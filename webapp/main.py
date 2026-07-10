import os
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config  # noqa: F401  (loads .env, extends sys.path)
from .auth import COOKIE_NAME, check_password, check_rate_limit, create_session_token, verify_session_token
from .chat import run_chat
from .config import COOKIE_SECURE

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="Dubai Real Estate Graph Assistant")


class LoginRequest(BaseModel):
    password: str


class ChatRequest(BaseModel):
    message: str
    history: list = []


def _session_token(request: Request) -> Optional[str]:
    return request.cookies.get(COOKIE_NAME)


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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
