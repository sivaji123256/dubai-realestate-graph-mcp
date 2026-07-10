import os
import time
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import graph_queries as gq

from . import config  # noqa: F401  (loads .env, extends sys.path)
from . import metrics
from .auth import COOKIE_NAME, check_password, check_rate_limit, create_session_token, verify_session_token
from .chat import run_chat
from .config import COOKIE_SECURE, OPENAI_MODEL

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="AqarIQ")


class LoginRequest(BaseModel):
    password: str


class ChatRequest(BaseModel):
    message: str
    history: list = []


def _session_token(request: Request) -> Optional[str]:
    return request.cookies.get(COOKIE_NAME)


def _require_auth(request: Request) -> Optional[JSONResponse]:
    if not verify_session_token(_session_token(request)):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return None


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


@app.post("/api/login")
def login(body: LoginRequest, response: Response):
    if not check_password(body.password):
        return JSONResponse({"ok": False, "error": "Incorrect password"}, status_code=401)
    token = create_session_token()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
    )
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return {"authenticated": verify_session_token(_session_token(request))}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    token = _session_token(request)
    if not verify_session_token(token):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    if not check_rate_limit(token):
        return JSONResponse({"error": "Rate limit exceeded, try again in a bit"}, status_code=429)
    if not body.message.strip():
        return JSONResponse({"error": "Empty message"}, status_code=400)
    reply = run_chat(body.message, body.history)
    return {"reply": reply}


@app.get("/api/dashboard/kpis")
def dashboard_kpis(request: Request):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.citywide_kpis()


@app.get("/api/dashboard/top-areas")
def dashboard_top_areas(request: Request, limit: int = 10):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.top_areas_by_volume(limit)


@app.get("/api/dashboard/price-trend")
def dashboard_price_trend(request: Request):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.citywide_monthly_trend()


@app.get("/api/dataset/versions")
def dataset_versions(request: Request):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.dataset_versions()


@app.get("/api/graph/area-subgraph")
def graph_area_subgraph(request: Request, area: str):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.area_subgraph(area)


@app.get("/api/graph/areas")
def graph_areas(request: Request):
    if (err := _require_auth(request)) is not None:
        return err
    return gq.list_areas()


@app.get("/api/metrics")
def metrics_snapshot(request: Request):
    if (err := _require_auth(request)) is not None:
        return err
    return metrics.snapshot(OPENAI_MODEL)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
