"""
Lightweight in-process observability. Resets on redeploy/restart -- there's
no persistent store for live request metrics (deliberately simple; dataset
provenance, which does need to survive restarts, is tracked separately in
Neo4j via graph_queries.dataset_versions()).
"""

import threading
import time
from collections import Counter, deque

_lock = threading.Lock()
_start_time = time.time()

_request_count = 0
_error_count = 0
_chat_message_count = 0
_status_counts = Counter()
_latencies_ms = deque(maxlen=200)
_prompt_tokens = 0
_completion_tokens = 0

# Published per-1M-token pricing (USD) used only for a rough spend estimate,
# not a billing-accurate figure. Update if the model/pricing changes.
_MODEL_PRICE_PER_1M = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
}


def record_request(endpoint: str, status_code: int, latency_ms: float):
    global _request_count, _error_count
    with _lock:
        _request_count += 1
        _status_counts[status_code] += 1
        _latencies_ms.append(latency_ms)
        if status_code >= 400:
            _error_count += 1


def record_chat_message():
    global _chat_message_count
    with _lock:
        _chat_message_count += 1


def record_tokens(prompt_tokens: int, completion_tokens: int):
    global _prompt_tokens, _completion_tokens
    with _lock:
        _prompt_tokens += prompt_tokens or 0
        _completion_tokens += completion_tokens or 0


def estimate_cost_usd(model: str) -> float:
    price = _MODEL_PRICE_PER_1M.get(model, _MODEL_PRICE_PER_1M["gpt-4o-mini"])
    return (_prompt_tokens / 1_000_000) * price["prompt"] + (_completion_tokens / 1_000_000) * price["completion"]


def public_snapshot() -> dict:
    """Public-safe subset for the /public Stats tab -- deliberately just
    uptime. No spend, tokens, or request/error counts: those are internal
    operational data about the business running this, not something an
    anonymous visitor should see (unlike snapshot() below, which is
    admin-only on the internal tool)."""
    with _lock:
        return {"uptime_seconds": round(time.time() - _start_time)}


def snapshot(model: str) -> dict:
    with _lock:
        latencies = list(_latencies_ms)
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        return {
            "uptime_seconds": round(time.time() - _start_time),
            "total_requests": _request_count,
            "error_count": _error_count,
            "chat_message_count": _chat_message_count,
            "avg_latency_ms": round(avg_latency, 1),
            "recent_latencies_ms": latencies[-50:],
            "status_counts": dict(_status_counts),
            "prompt_tokens": _prompt_tokens,
            "completion_tokens": _completion_tokens,
            "estimated_openai_spend_usd": round(estimate_cost_usd(model), 4),
        }
