import json
import logging

from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .openai_tools import TOOL_SCHEMAS, call_tool

logger = logging.getLogger(__name__)

_client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a Dubai real-estate market assistant backed by a live Neo4j graph \
of official Dubai Land Department (DLD) Sales transactions, covering a recent trailing window \
(call graph_schema to see the exact date range currently loaded).

DLD uses its own official area registry names, which can differ from popular marketing names \
(e.g. "Marsa Dubai" is the DLD name for the area popularly called "Dubai Marina"). If an area \
lookup returns zero results, call list_areas() to find the correct official name before giving up.

Always express prices in AED. When summarizing numbers, round sensibly and mention the \
transaction count so the user knows how much data backs a figure. Be concise but concrete -- \
prefer real numbers over vague statements."""

MAX_TOOL_ROUNDS = 5
MAX_TOKENS = 700
MAX_HISTORY_MESSAGES = 20


def run_chat(message: str, history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": message})

    for _ in range(MAX_TOOL_ROUNDS):
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            max_tokens=MAX_TOKENS,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = call_tool(tc.function.name, args)
                content = json.dumps(result, default=str)
            except Exception as e:
                logger.exception("Tool call failed: %s", tc.function.name)
                content = json.dumps({"error": str(e)})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    return (
        "I wasn't able to finish that within the allotted tool-call steps -- "
        "try breaking it into a simpler question."
    )
