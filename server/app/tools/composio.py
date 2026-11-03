"""Gmail + Google Calendar for Claude through Composio (REST v3.1, Composio-managed Google OAuth).

Flow (all from the admin page / iPhone app):
  1. the Composio project API key is saved once (CLAUDE_WORKDIR/composio_key, chmod 600);
  2. "Connect" per toolkit -> a Composio link for user `piko-owner` -> the owner approves Google in the browser;
  3. "Check" -> the connection is ACTIVE -> a Tool Router session is created once and its MCP URL is added to Claude's
     mcp.json (app/integrations.py), restricted to the tools below.
State (no secrets): DATA_DIR/composio.json.
"""
import json
import logging
import os
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger("composio")
BASE = "https://backend.composio.dev/api/v3.1"
KEY_FILE = Path(config.CLAUDE_WORKDIR) / "composio_key"
STATE_FILE = config.DATA_DIR / "composio.json"
USER_ID = "piko-owner"
TOOLKITS = {"gmail": "Gmail", "googlecalendar": "יומן Google"}
TOOLS = {
    "gmail": ["GMAIL_FETCH_EMAILS", "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID", "GMAIL_FETCH_MESSAGE_BY_THREAD_ID",
              "GMAIL_SEND_EMAIL", "GMAIL_REPLY_TO_THREAD", "GMAIL_CREATE_EMAIL_DRAFT"],
    "googlecalendar": ["GOOGLECALENDAR_EVENTS_LIST", "GOOGLECALENDAR_FIND_EVENT", "GOOGLECALENDAR_CREATE_EVENT",
                       "GOOGLECALENDAR_QUICK_ADD", "GOOGLECALENDAR_PATCH_EVENT", "GOOGLECALENDAR_DELETE_EVENT",
                       "GOOGLECALENDAR_FIND_FREE_SLOTS"],
}
STATUS = {"ACTIVE": "active", "INITIATED": "pending", "INITIALIZING": "pending", "FAILED": "failed",
          "EXPIRED": "expired", "INACTIVE": "expired", "REVOKED": "expired"}


def key() -> str:
    try:
        return KEY_FILE.read_text().strip()
    except OSError:
        return ""


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(s: dict):
    STATE_FILE.write_text(json.dumps(s, indent=1))


async def _req(method: str, path: str, k: str | None = None, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20) as c:
        return await c.request(method, BASE + path, headers={"x-api-key": k or key()}, **kw)


def _err(r: httpx.Response) -> str:
    try:
        e = r.json().get("error", {})
        return e.get("message") or r.text[:200]
    except ValueError:
        return r.text[:200]


async def set_key(k: str) -> dict:
    if len(k) < 10:
        return {"ok": False, "message": "המפתח קצר מדי"}
    try:
        r = await _req("GET", "/auth_configs", k, params={"limit": 1})
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"Composio לא עונה ({type(e).__name__})"}
    if r.status_code in (401, 403):
        return {"ok": False, "message": "המפתח לא התקבל ב-Composio"}
    if r.status_code >= 400:
        return {"ok": False, "message": _err(r)}
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = KEY_FILE.with_suffix(".tmp")
    tmp.write_text(k)
    os.chmod(tmp, 0o600)
    tmp.replace(KEY_FILE)
    _save_state({})                              # new key / project: old ids are meaningless
    log.info("Composio key saved")
    return {"ok": True}


async def _auth_config(toolkit: str) -> str:
    st = _state()
    ac = st.get("auth_configs", {}).get(toolkit)
    if ac:
        return ac
    r = await _req("GET", "/auth_configs", params={"toolkit_slug": toolkit, "is_composio_managed": "true", "limit": 50})
    r.raise_for_status()
    items = [i for i in r.json().get("items", []) if i.get("status", "ENABLED") == "ENABLED"]
    if items:
        ac = items[0]["id"]
    else:
        r = await _req("POST", "/auth_configs", json={"toolkit": {"slug": toolkit},
                                                    "auth_config": {"type": "use_composio_managed_auth", "name": f"piko-{toolkit}"}})
        if r.status_code >= 400:
            raise RuntimeError(_err(r))
        ac = r.json()["auth_config"]["id"]
    st.setdefault("auth_configs", {})[toolkit] = ac
    _save_state(st)
    return ac


async def connect(toolkit: str) -> dict:
    if toolkit not in TOOLKITS:
        return {"ok": False, "message": "שירות לא מוכר"}
    if not key():
        return {"ok": False, "message": "צריך קודם לשמור את המפתח של Composio"}
    try:
        ac = await _auth_config(toolkit)
        body = {"auth_config_id": ac, "user_id": USER_ID}
        cb = config.PUBLIC_URL or f"http://{config.LAN_IP}:{config.PORT}"
        body["callback_url"] = f"{cb}/admin"
        r = await _req("POST", "/connected_accounts/link", json=body)
        if r.status_code >= 400:
            return {"ok": False, "message": _err(r)}
        d = r.json()
        log.info("composio link for %s created", toolkit)
        return {"ok": True, "url": d.get("redirect_url"), "expires_at": d.get("expires_at")}
    except Exception as e:
        log.warning("composio connect %s: %s", toolkit, e)
        return {"ok": False, "message": f"לא הצלחתי להתחיל חיבור ({e})"[:200]}


async def _accounts() -> list[dict]:
    r = await _req("GET", "/connected_accounts", params={"user_ids": USER_ID, "toolkit_slugs": ",".join(TOOLKITS),
                                                       "order_by": "updated_at", "order_direction": "desc", "limit": 50})
    r.raise_for_status()
    return r.json().get("items", [])


async def status() -> dict:
    out = {"key": bool(key()), "toolkits": {k: {"name": n, "status": "none"} for k, n in TOOLKITS.items()}}
    if not key():
        return out
    try:
        items = await _accounts()
    except Exception as e:
        out["message"] = f"Composio לא עונה ({type(e).__name__})"
        return out
    rank = {"active": 4, "pending": 3, "expired": 2, "failed": 1, "none": 0}
    for it in items:
        tk = (it.get("toolkit") or {}).get("slug")
        if tk not in out["toolkits"] or it.get("is_disabled"):
            continue
        s = STATUS.get(it.get("status", ""), "none")
        if rank[s] > rank[out["toolkits"][tk]["status"]]:
            out["toolkits"][tk]["status"] = s
            out["toolkits"][tk]["id"] = it.get("id")
    active = [k for k, v in out["toolkits"].items() if v["status"] == "active"]
    st = _state()
    if active and not st.get("mcp_url"):
        await _ensure_session(st)
    if st.get("active") != active:
        st = _state()
        st["active"] = active
        _save_state(st)
    out["mcp"] = bool(_state().get("mcp_url"))
    return out


async def _ensure_session(st: dict):
    """One Tool Router session serving only the tools above; it uses whatever accounts are ACTIVE when a tool runs."""
    acs = {}
    for tk in TOOLKITS:
        try:
            acs[tk] = await _auth_config(tk)
        except Exception:
            pass
    full = {"user_id": USER_ID, "toolkits": {"enable": list(TOOLKITS)},
            "tools": {tk: {"enable": TOOLS[tk]} for tk in TOOLKITS}, "auth_configs": acs,
            "manage_connections": {"enable": False}, "workbench": {"enable": False}, "search": {"enable": False},
            "preload": {"tools": "all"}}
    minimal = {"user_id": USER_ID, "toolkits": {"enable": list(TOOLKITS)}, "tools": {tk: {"enable": TOOLS[tk]} for tk in TOOLKITS},
               "manage_connections": {"enable": False}}
    for body in (full, minimal):
        r = await _req("POST", "/tool_router/session", json=body)
        if r.status_code < 400:
            d = r.json()
            st = _state()
            st.update(session_id=d.get("session_id"), mcp_url=(d.get("mcp") or {}).get("url"))
            _save_state(st)
            log.info("composio session %s ready", st["session_id"])
            return
        log.warning("composio session: %s", _err(r))


async def disconnect(toolkit: str) -> dict:
    if toolkit not in TOOLKITS or not key():
        return {"ok": False}
    n = 0
    for it in await _accounts():
        if (it.get("toolkit") or {}).get("slug") == toolkit:
            r = await _req("DELETE", f"/connected_accounts/{it['id']}", params={"revoke_on_delete": "true"})
            n += r.status_code < 400
    st = _state()
    st["active"] = [t for t in st.get("active", []) if t != toolkit]
    _save_state(st)
    log.info("composio %s disconnected (%d accounts)", toolkit, n)
    return {"ok": True, "removed": n}


def mcp_entry() -> dict | None:
    st = _state()
    if not key() or not st.get("mcp_url") or not st.get("active"):
        return None
    return {"type": "http", "url": st["mcp_url"], "headers": {"x-api-key": key()}}
