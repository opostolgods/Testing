"""3X-UI API client for managing VPN keys on free and premium servers."""
from __future__ import annotations

import json
import logging
import random
import time
import uuid
from typing import Optional

import httpx

from config import (
    FREE_SERVER_IP, FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS, FREE_INBOUND_ID,
    PREMIUM_SERVER_IP, PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS,
    PREMIUM_INBOUND_ID, FREE_TRIAL_DAYS, SUBSCRIPTION_DAYS,
)

logger = logging.getLogger(__name__)

FINGERPRINTS = ["chrome", "firefox", "edge", "safari"]

_sessions: dict[str, dict] = {}


async def _login(base_url: str, username: str, password: str) -> str:
    key = base_url
    s = _sessions.get(key, {})
    if s.get("cookie") and time.time() - s.get("ts", 0) < 3500:
        return s["cookie"]

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/login",
            data={"username": username, "password": password},
        )
        cookies = resp.headers.get_all("set-cookie") if hasattr(resp.headers, 'get_all') else []
        if not cookies:
            for k, v in resp.headers.multi_items():
                if k.lower() == "set-cookie":
                    cookies.append(v)

        for c in cookies:
            if "3x-ui" in c or "session" in c.lower():
                cookie = c.split(";")[0]
                _sessions[key] = {"cookie": cookie, "ts": time.time()}
                return cookie

        body = resp.json()
        if body.get("success") and cookies:
            cookie = cookies[0].split(";")[0]
            _sessions[key] = {"cookie": cookie, "ts": time.time()}
            return cookie

    return ""


async def _get_inbound(base_url: str, username: str, password: str,
                       inbound_id: int) -> Optional[dict]:
    cookie = await _login(base_url, username, password)
    if not cookie:
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{base_url}/panel/api/inbounds/get/{inbound_id}",
            headers={"Cookie": cookie},
        )
        result = resp.json()
        if result.get("success"):
            return result["obj"]
    return None


async def _add_client(base_url: str, username: str, password: str,
                      inbound_id: int, client_data: dict) -> bool:
    cookie = await _login(base_url, username, password)
    if not cookie:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/panel/api/inbounds/addClient",
            data={
                "id": inbound_id,
                "settings": json.dumps({"clients": [client_data]}),
            },
            headers={"Cookie": cookie},
        )
        result = resp.json()
        return result.get("success", False)


async def _del_client(base_url: str, username: str, password: str,
                      inbound_id: int, client_uuid: str) -> bool:
    cookie = await _login(base_url, username, password)
    if not cookie:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
            headers={"Cookie": cookie},
        )
        result = resp.json()
        return result.get("success", False)


async def _get_client_traffic(base_url: str, username: str, password: str,
                              email: str) -> Optional[dict]:
    cookie = await _login(base_url, username, password)
    if not cookie:
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{base_url}/panel/api/inbounds/getClientTraffics/{email}",
            headers={"Cookie": cookie},
        )
        result = resp.json()
        if result.get("success") and result.get("obj"):
            return result["obj"]
    return None


def _get_reality_keys(inbound_obj: dict) -> tuple[str, list, list]:
    stream = json.loads(inbound_obj.get("streamSettings", "{}"))
    reality = stream.get("realitySettings", {})
    settings = reality.get("settings", {})
    public_key = settings.get("publicKey", "")
    short_ids = reality.get("shortIds", [])
    server_names = reality.get("serverNames", ["www.google.com"])
    return public_key, short_ids, server_names


def _build_vless_link(client_uuid: str, name: str, server_ip: str,
                      port: int, public_key: str, short_ids: list,
                      server_names: list, label_suffix: str = "") -> str:
    sid = random.choice(short_ids) if short_ids else ""
    sni = random.choice(server_names) if server_names else "www.google.com"
    fp = random.choice(FINGERPRINTS)
    label = f"CloudVPN-{label_suffix}-{name}" if label_suffix else f"CloudVPN-{name}"

    params = (
        f"type=tcp&security=reality&pbk={public_key}"
        f"&fp={fp}&sni={sni}&sid={sid}&spx=%2F&flow=xtls-rprx-vision"
    )
    return f"vless://{client_uuid}@{server_ip}:{port}?{params}#{label}"


async def get_reality_keys_for_server(server: str = "free") -> tuple[str, list, list]:
    if server == "premium":
        ib = await _get_inbound(
            PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS, PREMIUM_INBOUND_ID
        )
    else:
        ib = await _get_inbound(
            FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS, FREE_INBOUND_ID
        )
    if not ib:
        return "", [], []
    return _get_reality_keys(ib)


async def create_key(email: str, is_premium: bool = False,
                     days: int = 0) -> Optional[dict]:
    """Create VPN key. Premium users get keys on both servers."""
    if not days:
        days = SUBSCRIPTION_DAYS if is_premium else FREE_TRIAL_DAYS

    expiry_ms = int((time.time() + days * 86400) * 1000)
    client_uuid = str(uuid.uuid4())
    sub_id = str(uuid.uuid4())[:8]

    client_data = {
        "id": client_uuid,
        "email": email,
        "enable": True,
        "expiryTime": expiry_ms,
        "limitIp": 3 if is_premium else 1,
        "totalGB": 0,
        "subId": sub_id,
        "flow": "xtls-rprx-vision",
        "tgId": "",
    }

    free_ok = await _add_client(
        FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS,
        FREE_INBOUND_ID, client_data,
    )
    if not free_ok:
        logger.error(f"Failed to create free key for {email}")
        return None

    premium_ok = False
    if is_premium:
        premium_ok = await _add_client(
            PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS,
            PREMIUM_INBOUND_ID, client_data,
        )
        if not premium_ok:
            logger.warning(f"Failed to create premium key for {email}")

    free_pbk, free_sids, free_sns = await get_reality_keys_for_server("free")
    links = []
    if free_pbk:
        links.append(_build_vless_link(
            client_uuid, email, FREE_SERVER_IP, 443,
            free_pbk, free_sids, free_sns, "Free",
        ))

    if is_premium and premium_ok:
        prem_pbk, prem_sids, prem_sns = await get_reality_keys_for_server("premium")
        if prem_pbk:
            links.append(_build_vless_link(
                client_uuid, email, PREMIUM_SERVER_IP, 443,
                prem_pbk, prem_sids, prem_sns, "Premium",
            ))

    return {
        "uuid": client_uuid,
        "sub_id": sub_id,
        "email": email,
        "links": links,
        "expiry_ms": expiry_ms,
        "is_premium": is_premium,
        "days": days,
    }


async def delete_key(client_uuid: str) -> bool:
    free_ok = await _del_client(
        FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS,
        FREE_INBOUND_ID, client_uuid,
    )
    await _del_client(
        PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS,
        PREMIUM_INBOUND_ID, client_uuid,
    )
    return free_ok


async def get_traffic(email: str) -> dict:
    result = {"up": 0, "down": 0, "total": 0}

    free_traffic = await _get_client_traffic(
        FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS, email,
    )
    if free_traffic:
        result["up"] += free_traffic.get("up", 0)
        result["down"] += free_traffic.get("down", 0)

    prem_traffic = await _get_client_traffic(
        PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS, email,
    )
    if prem_traffic:
        result["up"] += prem_traffic.get("up", 0)
        result["down"] += prem_traffic.get("down", 0)

    result["total"] = result["up"] + result["down"]
    return result


async def get_all_clients(server: str = "free") -> list[dict]:
    if server == "premium":
        ib = await _get_inbound(
            PREMIUM_XUI_URL, PREMIUM_XUI_USER, PREMIUM_XUI_PASS, PREMIUM_INBOUND_ID
        )
    else:
        ib = await _get_inbound(
            FREE_XUI_URL, FREE_XUI_USER, FREE_XUI_PASS, FREE_INBOUND_ID
        )
    if not ib:
        return []
    settings = json.loads(ib.get("settings", "{}"))
    return settings.get("clients", [])
