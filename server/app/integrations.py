"""Connections of Piko's brain to other services, managed from the admin page.

- Home Assistant: a long-lived token in CLAUDE_WORKDIR/ha_token (chmod 600). Used by app/tools/ha.py (REST: the board's
  Home page, cards, cameras) and by Claude through Home Assistant's own MCP server (voice control).
- Composio (Gmail + Google Calendar): see app/tools/composio.py; its MCP entry is added here when connected.

Claude's MCP config (CLAUDE_WORKDIR/mcp.json) is rebuilt from these pieces whenever one changes, then the CLI restarts.
"""
import json
import logging
import os
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("integrations")
WORK = Path(config.CLAUDE_WORKDIR)
HA_TOKEN_FILE = WORK / "ha_token"
MCP_FILE = WORK / "mcp.json"


def _write_secret(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o600)
    tmp.replace(p)


# ---------------------------------------------------------------- Home Assistant
def ha_token() -> str:
    if config.HA_TOKEN:
        return config.HA_TOKEN
    try:
        return HA_TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


async def ha_check(token: str | None = None) -> dict:
    """{ok, message, mcp}: the API answers with this token, and whether HA's MCP server integration is on."""
    token = token if token is not None else ha_token()
    if not token:
        return {"ok": False, "message": "אין טוקן", "mcp": False}
    h = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get(f"{config.HA_URL}/api/", headers=h)
            if r.status_code == 401:
                return {"ok": False, "message": "הטוקן לא תקף", "mcp": False}
            r.raise_for_status()
            mcp = False
            try:
                e = await c.get(f"{config.HA_URL}/api/config/config_entries/entry", headers=h)
                mcp = any(x.get("domain") == "mcp_server" for x in e.json())
            except Exception:
                pass
            return {"ok": True, "message": "מחובר", "mcp": mcp}
    except Exception as ex:
        return {"ok": False, "message": f"Home Assistant לא עונה ({type(ex).__name__})", "mcp": False}


async def ha_enable_mcp(token: str) -> bool:
    """Turns on HA's 'Model Context Protocol Server' integration (Assist API) if it is not on yet."""
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            e = await c.get(f"{config.HA_URL}/api/config/config_entries/entry", headers=h)
            if any(x.get("domain") == "mcp_server" for x in e.json()):
                return True
            f = (await c.post(f"{config.HA_URL}/api/config/config_entries/flow", headers=h, json={"handler": "mcp_server"})).json()
            fid = f.get("flow_id")
            if fid:
                await c.post(f"{config.HA_URL}/api/config/config_entries/flow/{fid}", headers=h, json={"llm_hass_api": ["assist"]})
            e = await c.get(f"{config.HA_URL}/api/config/config_entries/entry", headers=h)
            return any(x.get("domain") == "mcp_server" for x in e.json())
    except Exception as ex:
        log.warning("enable HA MCP: %s", ex)
        return False


async def ha_set_token(token: str) -> dict:
    token = token.strip()
    st = await ha_check(token)
    if not st["ok"]:
        return st
    _write_secret(HA_TOKEN_FILE, token)
    st["mcp"] = await ha_enable_mcp(token)
    write_mcp()
    log.info("Home Assistant token saved (mcp=%s)", st["mcp"])
    return st


def ha_forget():
    HA_TOKEN_FILE.unlink(missing_ok=True)
    write_mcp()


# ---------------------------------------------------------------- Claude's MCP config
def write_mcp() -> dict:
    """Rebuilds mcp.json from the configured services. Returns the server names."""
    servers: dict = {}
    tok = ha_token()
    if tok:
        servers["homeassistant"] = {"type": "http", "url": f"{config.HA_URL}/api/mcp",
                                    "headers": {"Authorization": f"Bearer {tok}"}}
    try:
        from .tools import composio
        entry = composio.mcp_entry()
        if entry:
            servers["composio"] = entry
    except Exception as ex:
        log.warning("composio mcp entry: %s", ex)
    if servers:
        _write_secret(MCP_FILE, json.dumps({"mcpServers": servers}))
    else:
        MCP_FILE.unlink(missing_ok=True)
    log.info("mcp.json: %s", ", ".join(servers) or "(none)")
    return servers


def mcp_names() -> list[str]:
    try:
        return list(json.loads(MCP_FILE.read_text()).get("mcpServers", {}))
    except (OSError, ValueError):
        return []


def startup():
    """Migrates a token that only lives in an older mcp.json (script 13) into ha_token, then rebuilds mcp.json."""
    if not ha_token():
        try:
            hdr = json.loads(MCP_FILE.read_text())["mcpServers"]["homeassistant"]["headers"]["Authorization"]
            if hdr.lower().startswith("bearer "):
                _write_secret(HA_TOKEN_FILE, hdr[7:].strip())
                log.info("Home Assistant token migrated from mcp.json")
        except (OSError, ValueError, KeyError, TypeError):
            pass
    write_mcp()
