import time
from collections import defaultdict, deque
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import user_store
from .config import SESSION_SECRET

COOKIE_NAME = "session"
MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

_serializer = URLSafeTimedSerializer(SESSION_SECRET)


def create_session_token(email: str) -> str:
    return _serializer.dumps({"email": email})


def _decode_email(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=MAX_AGE_SECONDS)
        return data.get("email")
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(token: Optional[str]) -> Optional[dict]:
    """Resolves a session cookie to the live user record, re-fetched from
    Neo4j on every call -- so a deactivated account is locked out
    immediately rather than only once its token expires."""
    email = _decode_email(token)
    if not email:
        return None
    user = user_store.get_user(email)
    if not user or not user.get("active"):
        return None
    return user


# Lightweight in-memory rate limiter -- a secondary guard against runaway
# OpenAI cost on top of login (or, for the public endpoint, the only guard
# since there's no login). Not distributed -- fine for a single Render
# instance; resets on redeploy/restart.
_RATE_LIMIT_WINDOW_SECONDS = 3600
_hits = defaultdict(deque)

RATE_LIMIT_AUTHENTICATED = 40  # per logged-in user, per hour
RATE_LIMIT_PUBLIC = 15  # per IP, per hour -- tighter since there's no account behind it
RATE_LIMIT_PUBLIC_READ = 60  # per IP, per hour -- dashboard/graph reads have no OpenAI cost, more generous


def check_rate_limit(key: str, max_per_hour: int = RATE_LIMIT_AUTHENTICATED) -> bool:
    """Returns True if the request is allowed, False if rate-limited."""
    now = time.time()
    window = _hits[key]
    while window and now - window[0] > _RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= max_per_hour:
        return False
    window.append(now)
    return True
