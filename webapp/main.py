import json
import os
import time
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import graph_queries as gq

from . import config  # noqa: F401  (loads .env, extends sys.path)
from . import metrics, user_store
from .auth import (
    COOKIE_NAME,
    RATE_LIMIT_PUBLIC,
    check_rate_limit,
    create_session_token,
    get_current_user,
)
from .chat import run_chat
from .config import COOKIE_SECURE, OPENAI_MODEL
from .public_chat import run_public_chat, run_public_chat_stream

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="AqarIQ")


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str
    history: list = []


class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "rep"


def _session_token(request: Request) -> Optional[str]:
    return request.cookies.get(COOKIE_NAME)


def _client_ip(request: Request) -> str:
    """Render sits behind a proxy -- the real client IP is in
    X-Forwarded-For (first entry), not request.client.host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _current_user(request: Request) -> Optional[dict]:
    return get_current_user(_session_token(request))


def _require_auth(request: Request):
    """Returns (user, None) if authenticated, or (None, error_response)."""
    user = _current_user(request)
    if user is None:
        return None, JSONResponse({"error": "Not authenticated"}, status_code=401)
    return user, None


def _require_admin(request: Request):
    user, err = _require_auth(request)
    if err is not None:
        return None, err
    if user["role"] != "admin":
        return None, JSONResponse({"error": "Admin access required"}, status_code=403)
    return user, None


@app.middleware("http")
async def track_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000
    metrics.record_request(request.url.path, response.status_code, latency_ms)
    return response


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/public")
def public_index():
    return FileResponse(os.path.join(STATIC_DIR, "public.html"))


@app.post("/api/public/chat")
def public_chat(body: ChatRequest, request: Request):
    ip = _client_ip(request)
    if not check_rate_limit(f"ip:{ip}", max_per_hour=RATE_LIMIT_PUBLIC):
        return JSONResponse({"error": "Rate limit exceeded, try again in a bit"}, status_code=429)
    if not body.message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)
    reply = run_public_chat(body.message, body.history)
    return {"reply": reply}


@app.post("/api/public/chat/stream")
def public_chat_stream(body: ChatRequest, request: Request):
    """Server-Sent Events version of /api/public/chat -- yields live
    step events (tool calls, results) as the agent works, then a final
    event with the answer. See webapp/chat.py's run_chat_loop_stream."""
    ip = _client_ip(request)
    if not check_rate_limit(f"ip:{ip}", max_per_hour=RATE_LIMIT_PUBLIC):
        return JSONResponse({"error": "Rate limit exceeded, try again in a bit"}, status_code=429)
    if not body.message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)

    def event_stream():
        for event in run_public_chat_stream(body.message, body.history):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/login")
def login(body: LoginRequest, response: Response):
    user = user_store.get_user(body.email)
    if (
        not user
        or not user["active"]
        or not user_store.verify_password(body.password, user["password_hash"])
    ):
        return JSONResponse({"ok": False, "error": "Invalid email or password"}, status_code=401)
    token = create_session_token(user["email"])
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return {"ok": True, "name": user["name"], "role": user["role"]}


@app.get("/api/me")
def me(request: Request):
    user = _current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "email": user["email"], "name": user["name"], "role": user["role"]}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    user, err = _require_auth(request)
    if err is not None:
        return err
    if not check_rate_limit(f"user:{user['email']}"):
        return JSONResponse({"error": "Rate limit exceeded, try again in a bit"}, status_code=429)
    if not body.message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)
    reply = run_chat(body.message, body.history)
    user_store.record_activity(user["email"])
    return {"reply": reply}


@app.get("/api/dashboard/kpis")
def dashboard_kpis(request: Request):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.citywide_kpis()


@app.get("/api/dashboard/top-areas")
def dashboard_top_areas(request: Request, limit: int = 10):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.top_areas_by_volume(limit)


@app.get("/api/dashboard/price-trend")
def dashboard_price_trend(request: Request):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.citywide_monthly_trend()


@app.get("/api/dataset/versions")
def dataset_versions(request: Request):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.dataset_versions()


@app.get("/api/graph/area-subgraph")
def graph_area_subgraph(request: Request, area: str):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.area_subgraph(area)


@app.get("/api/graph/areas")
def graph_areas(request: Request):
    if (err := _require_auth(request)[1]) is not None:
        return err
    return gq.list_areas()


@app.get("/api/metrics")
def metrics_snapshot(request: Request):
    if (err := _require_admin(request)[1]) is not None:
        return err
    return metrics.snapshot(OPENAI_MODEL)


@app.get("/api/team/users")
def team_users(request: Request):
    if (err := _require_admin(request)[1]) is not None:
        return err
    return user_store.list_users()


@app.post("/api/team/users")
def team_create_user(body: CreateUserRequest, request: Request):
    if (err := _require_admin(request)[1]) is not None:
        return err
    if user_store.get_user(body.email):
        return JSONResponse({"error": "A user with that email already exists"}, status_code=409)
    return user_store.create_user(body.email, body.name, body.password, body.role)


@app.post("/api/team/users/{email}/deactivate")
def team_deactivate_user(email: str, request: Request):
    if (err := _require_admin(request)[1]) is not None:
        return err
    user_store.set_active(email, False)
    return {"ok": True}


@app.post("/api/team/users/{email}/activate")
def team_activate_user(email: str, request: Request):
    if (err := _require_admin(request)[1]) is not None:
        return err
    user_store.set_active(email, True)
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
