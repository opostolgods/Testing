"""CloudVPN Web Application — FastAPI backend."""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import (
    BOT_TOKEN, BOT_USERNAME, ADMIN_IDS, SECRET_KEY,
    DOMAIN, SUPPORT_USERNAME,
)
from database import init_db, upsert_user, get_user, get_user_keys, save_key
from database import deactivate_key, set_premium, get_all_users, get_all_keys, get_stats
from xui_client import create_key, delete_key, get_traffic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudvpn")

app = FastAPI(title="CloudVPN", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: dict[str, dict] = {}
SESSION_TTL = 86400


def verify_telegram_auth(data: dict) -> bool:
    check_hash = data.pop("hash", "")
    sorted_data = "\n".join(f"{k}={data[k]}" for k in sorted(data) if data[k])
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed = hmac.new(secret, sorted_data.encode(), hashlib.sha256).hexdigest()
    data["hash"] = check_hash
    return computed == check_hash


def get_session_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session") or request.headers.get("X-Session-Token", "")
    if not token:
        return None
    session = SESSIONS.get(token)
    if not session:
        return None
    if time.time() - session.get("ts", 0) > SESSION_TTL:
        SESSIONS.pop(token, None)
        return None
    return session.get("user")


def require_auth(request: Request) -> dict:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request) -> dict:
    user = require_auth(request)
    if user.get("telegram_id") not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Auth ────────────────────────────────────────────────

@app.post("/api/auth/telegram")
async def auth_telegram(request: Request):
    data = await request.json()

    auth_data = {k: str(v) for k, v in data.items() if k != "hash"}
    auth_data_with_hash = {**auth_data, "hash": data.get("hash", "")}

    if not verify_telegram_auth(auth_data_with_hash):
        raise HTTPException(status_code=400, detail="Invalid auth data")

    auth_date = int(data.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        raise HTTPException(status_code=400, detail="Auth data expired")

    telegram_id = int(data["id"])
    is_admin = telegram_id in ADMIN_IDS

    user = upsert_user(
        telegram_id=telegram_id,
        username=data.get("username", ""),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        photo_url=data.get("photo_url", ""),
        is_admin=is_admin,
    )

    token = secrets.token_hex(32)
    SESSIONS[token] = {"user": user, "ts": time.time()}

    response = JSONResponse({"ok": True, "user": user, "is_admin": is_admin})
    response.set_cookie(
        "session", token,
        httponly=True, secure=True, samesite="lax",
        max_age=SESSION_TTL,
    )
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    token = request.cookies.get("session", "")
    SESSIONS.pop(token, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session")
    return response


@app.get("/api/auth/me")
async def get_me(user: dict = Depends(require_auth)):
    return {"ok": True, "user": user}


# ── User Dashboard ──────────────────────────────────────

@app.get("/api/keys")
async def list_keys(user: dict = Depends(require_auth)):
    keys = get_user_keys(user["telegram_id"])
    for k in keys:
        if k.get("vless_links"):
            k["vless_links"] = json.loads(k["vless_links"])
    return {"ok": True, "keys": keys}


@app.post("/api/keys/create")
async def create_new_key(request: Request, user: dict = Depends(require_auth)):
    existing = get_user_keys(user["telegram_id"])
    is_premium = bool(user.get("is_premium"))

    max_keys = 5 if is_premium else 1
    active_keys = [k for k in existing if k.get("active")]
    if len(active_keys) >= max_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {max_keys} active keys allowed",
        )

    email = f"web_{user['telegram_id']}_{int(time.time())}"
    key_data = await create_key(email=email, is_premium=is_premium)
    if not key_data:
        raise HTTPException(status_code=500, detail="Failed to create key")

    save_key(user["telegram_id"], key_data)

    return {"ok": True, "key": key_data}


@app.delete("/api/keys/{key_uuid}")
async def remove_key(key_uuid: str, user: dict = Depends(require_auth)):
    keys = get_user_keys(user["telegram_id"])
    key = next((k for k in keys if k["uuid"] == key_uuid), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    await delete_key(key_uuid)
    deactivate_key(key_uuid)
    return {"ok": True}


@app.get("/api/keys/{key_uuid}/traffic")
async def key_traffic(key_uuid: str, user: dict = Depends(require_auth)):
    keys = get_user_keys(user["telegram_id"])
    key = next((k for k in keys if k["uuid"] == key_uuid), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    traffic = await get_traffic(key["email"])
    return {"ok": True, "traffic": traffic}


# ── Admin ───────────────────────────────────────────────

@app.get("/api/admin/stats")
async def admin_stats(user: dict = Depends(require_admin)):
    stats = get_stats()
    return {"ok": True, "stats": stats}


@app.get("/api/admin/users")
async def admin_users(user: dict = Depends(require_admin)):
    users = get_all_users()
    return {"ok": True, "users": users}


@app.get("/api/admin/keys")
async def admin_keys(user: dict = Depends(require_admin)):
    keys = get_all_keys()
    for k in keys:
        if k.get("vless_links"):
            k["vless_links"] = json.loads(k["vless_links"])
    return {"ok": True, "keys": keys}


@app.post("/api/admin/users/{telegram_id}/premium")
async def admin_set_premium(telegram_id: int, request: Request,
                            user: dict = Depends(require_admin)):
    body = await request.json()
    set_premium(telegram_id, body.get("is_premium", True))
    return {"ok": True}


# ── Config / Info ───────────────────────────────────────

@app.get("/api/config")
async def get_config():
    return {
        "bot_username": BOT_USERNAME,
        "support": SUPPORT_USERNAME,
        "domain": DOMAIN,
    }


# ── Static files ────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = os.path.join(FRONTEND_DIR, path)
        if path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ── Startup ─────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("CloudVPN backend started")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
