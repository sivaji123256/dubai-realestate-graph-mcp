import json
import logging

from openai import OpenAI

from . import metrics
from .config import OPENAI_API_KEY, OPENAI_MODEL
from .openai_tools import TOOL_SCHEMAS, call_tool, friendly_tool_label, summarize_result

logger = logging.getLogger(__name__)

_client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a Dubai real-estate market assistant backed by a live Neo4j graph \
of official Dubai Land Department (DLD) Sales transactions, covering a recent trailing window \
(call graph_schema to see the exact date range currently loaded).

Area and metro-station names are resolved automatically server-side (typos, common popular names \
like "Dubai Marina" -> "Marsa Dubai", and known zone names like "DMCC" -> "Jumeirah Lakes Towers" \
are all handled for you) -- pass whatever name the user gave you as-is, don't try to guess or \
rewrite it yourself. Tool results include a `resolved_area_name` field when a name was \
reinterpreted; mention the official DLD name in your answer so the user understands the mapping. \
If a tool genuinely returns zero results, that means the name truly didn't resolve -- call \
list_areas() or list_metro_stations() to see what's actually available and say so honestly, \
rather than guessing a plausible-sounding answer.

compare_areas deduplicates names that resolve to the same official area (e.g. asking to compare \
"Dubai Marina" and "Marsa Dubai" returns one row, not two) -- never add up numbers across rows \
yourself; report exactly what each row says, and if fewer rows come back than areas you asked \
for, that means some of them were the same place.

Always express prices in AED. When summarizing numbers, round sensibly and mention the \
transaction count so the user knows how much data backs a figure. Be concise but concrete -- \
prefer real numbers over vague statements."""

MAX_TOOL_ROUNDS = 5
MAX_TOKENS = 700
MAX_HISTORY_MESSAGES = 20


def run_chat(message: str, history: list) -> str:
    metrics.record_chat_message()
    return run_chat_loop(SYSTEM_PROMPT, message, history)


def run_chat_loop_stream(system_prompt: str, message: str, history: list, max_rounds: int = MAX_TOOL_ROUNDS):
    """Generator version of the tool-calling loop -- yields step events as
    the agent works ({"type": "tool_call", ...}, {"type": "tool_result",
    ...}) and finally {"type": "final", "content": ...}. Consumed directly
    by the streaming /public endpoint for live visibility into what the
    agent is doing; run_chat_loop() below wraps this for callers that just
    want the final answer string."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": message})

    for _ in range(max_rounds):
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            max_tokens=MAX_TOKENS,
        )
        if response.usage:
            metrics.record_tokens(response.usage.prompt_tokens, response.usage.completion_tokens)
        msg = response.choices[0].message

        if not msg.tool_calls:
            yield {"type": "final", "content": msg.content or ""}
            return

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            yield {
                "type": "tool_call",
                "tool": tc.function.name,
                "friendly": friendly_tool_label(tc.function.name, args),
            }
            try:
                result = call_tool(tc.function.name, args)
                content = json.dumps(result, default=str)
                yield {"type": "tool_result", "tool": tc.function.name, "summary": summarize_result(result)}
            except Exception as e:
                logger.exception("Tool call failed: %s", tc.function.name)
                content = json.dumps({"error": str(e)})
                yield {"type": "tool_result", "tool": tc.function.name, "summary": "No data found"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    yield {
        "type": "final",
        "content": (
            "I wasn't able to finish that within the allotted tool-call steps -- "
            "try breaking it into a simpler question."
        ),
    }


def run_chat_loop(system_prompt: str, message: str, history: list, max_rounds: int = MAX_TOOL_ROUNDS) -> str:
    """Non-streaming wrapper around run_chat_loop_stream -- returns just the
    final answer text. Used by the internal (authenticated) chat, which
    doesn't need live step visibility."""
    for event in run_chat_loop_stream(system_prompt, message, history, max_rounds):
        if event["type"] == "final":
            return event["content"]
    return ""
