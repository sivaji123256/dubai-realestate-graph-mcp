import time
from collections import defaultdict, deque

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import APP_PASSWORD, SESSION_SECRET

COOKIE_NAME = "session"
MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

_serializer = URLSafeTimedSerializer(SESSION_SECRET)


def check_password(password: str) -> bool:
    return password == APP_PASSWORD


def create_session_token() -> str:
    return _serializer.dumps({"ok": True})


def verify_session_token(token: str) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


# Lightweight in-memory rate limiter, per session token, as a secondary guard
# against runaway OpenAI cost on top of the password gate. Not distributed --
# fine for a single Render instance; resets on redeploy/restart.
_RATE_LIMIT_MAX = 40
_RATE_LIMIT_WINDOW_SECONDS = 3600
_hits = defaultdict(deque)


def check_rate_limit(session_key: str) -> bool:
    """Returns True if the request is allowed, False if rate-limited."""
    now = time.time()
    window = _hits[session_key]
    while window and now - window[0] > _RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= _RATE_LIMIT_MAX:
        return False
    window.append(now)
    return True
