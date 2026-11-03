"""Web admin: status, settings, expressions, meetings, logs and OTA at /admin.

Login without passwords: a one-time code (valid 3 minutes, single use) is created on the server with
    runuser -u companion -- /opt/companion/venv/bin/python -m tools.admin_link
and opened as /admin/login?code=...; it becomes an HttpOnly session cookie for 30 days. API calls also accept
the device token as a Bearer header (scripts).

Settings that can change at runtime are kept in DATA_DIR/settings.json and applied over /etc/companion.env.
"""
import asyncio
import collections
import hashlib
import json
import logging
import secrets
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from . import config

log = logging.getLogger("admin")
AUTH_FILE = config.DATA_DIR / "admin.json"
SETTINGS_FILE = config.DATA_DIR / "settings.json"
PAGE = Path(__file__).with_name("admin_page.html")
COOKIE = "piko_admin"
CODE_TTL, SESSION_TTL = 180, 30 * 24 * 3600
STARTED = time.time()

# ---------------------------------------------------------------- log ring buffer (shown in the page)
LOG_LINES: collections.deque = collections.deque(maxlen=400)


class _Ring(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            for key in ("token=", "code="):          # never show secrets in the page
                if key in msg:
                    msg = msg.split(key)[0] + key + "…"
            LOG_LINES.append(msg)
        except Exception:
            pass


_h = _Ring()
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))


# ---------------------------------------------------------------- auth
def _h256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _load() -> dict:
    try:
        d = json.loads(AUTH_FILE.read_text())
    except (OSError, ValueError):
        d = {}
    now = time.time()
    for k in ("codes", "sessions"):
        d[k] = {h: exp for h, exp in d.get(k, {}).items() if exp > now}
    return d


def _save(d: dict):
    AUTH_FILE.write_text(json.dumps(d))
    AUTH_FILE.chmod(0o600)


def new_code(pair: bool = False) -> str:
    """One-time login code: a long link code (scripts), or 6 digits typed in the iPhone app (pairing, 5 minutes)."""
    code = f"{secrets.randbelow(10**6):06d}" if pair else secrets.token_urlsafe(18)
    d = _load()
    d["codes"][_h256(code)] = time.time() + (300 if pair else CODE_TTL)
    _save(d)
    return code


_fails: list[float] = []


def _too_many_fails() -> bool:
    now = time.time()
    _fails[:] = [t for t in _fails if now - t < 300]
    return len(_fails) >= 10


def _authed(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and config.DEVICE_TOKEN and secrets.compare_digest(auth[7:], config.DEVICE_TOKEN):
        return True
    sid = request.cookies.get(COOKIE)
    return bool(sid) and _h256(sid) in _load()["sessions"]


def _need(request: Request):
    if not _authed(request):
        raise HTTPException(401, "login required")


# ---------------------------------------------------------------- settings
EDITABLE = {   # key: (config attribute, type, validator)
    "tts_provider": ("TTS_PROVIDER", str, lambda v: v in ("edge", "elevenlabs")),
    "tts_style": ("TTS_STYLE", str, lambda v: v in ("natural", "lively")),
    "elevenlabs_voice_id": ("ELEVENLABS_VOICE_ID", str, lambda v: 1<=len(v)<=100 and all(c.isalnum() or c in "_-" for c in v)),
    "elevenlabs_model": ("ELEVENLABS_MODEL", str, lambda v: 1<=len(v)<=100 and all(c.isalnum() or c in "_-" for c in v)),
    "live_transcription": (None, bool, lambda v: type(v) is bool),
    "tts_voice": ("TTS_VOICE", str, lambda v: v in ("he-IL-HilaNeural", "he-IL-AvriNeural")),
    "tts_rate": ("TTS_RATE", str, lambda v: v[:1] in "+-" and v.endswith("%") and abs(int(v[1:-1])) <= 50),
    "claude_model": ("CLAUDE_MODEL", str, lambda v: v in ("haiku", "sonnet", "opus")),
    "owner": ("OWNER", str, lambda v: 0 < len(v) <= 30),
    "name": ("NAME", str, lambda v: 0 < len(v) <= 30),
    "city": ("CITY", str, lambda v: 0 < len(v) <= 40),
    "lat": ("LAT", float, lambda v: -90 <= v <= 90),
    "lon": ("LON", float, lambda v: -180 <= v <= 180),
    "brightness": (None, int, lambda v: 20 <= v <= 255),
    "volume": (None, int, lambda v: 0 <= v <= 100),
    "hold_to_talk": (None, bool, lambda v: type(v) is bool),
    "shake_reaction": (None, bool, lambda v: type(v) is bool),
    "character_sounds": (None, bool, lambda v: type(v) is bool),
    "reduced_motion": (None, bool, lambda v: type(v) is bool),
    "dim_seconds": (None, int, lambda v: 5 <= v <= 30),
    "sleep_seconds": (None, int, lambda v: 60 <= v <= 3600),
}


def settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def apply_settings():
    for k, v in settings().items():
        attr = EDITABLE.get(k, (None,))[0]
        if attr:
            setattr(config, attr, v)


def current_settings() -> dict:
    s = settings()
    out = {k: getattr(config, a) for k, (a, _, _) in EDITABLE.items() if a}
    out["brightness"] = s.get("brightness", 170)
    out["volume"] = s.get("volume", 80)
    for key,default in {"live_transcription":False,"character_sounds":True,"hold_to_talk":True,"shake_reaction":True,"reduced_motion":False,"dim_seconds":15,"sleep_seconds":300}.items():out[key]=s.get(key,default)
    return out


# ---------------------------------------------------------------- routes
def register(app, ctx: SimpleNamespace):
    """ctx: hub, brain, converse, emotion_names, battery, calendar, meeting_mod, last_latency (dict)"""
    apply_settings()
    logging.getLogger().addHandler(_h)       # after logging.basicConfig() in main, so the journal output stays
    brain_cache = {"t": 0.0, "v": {}}

    async def brain_status():
        if time.time() - brain_cache["t"] > 60:
            brain_cache.update(t=time.time(), v=await ctx.brain.status())
        return brain_cache["v"]

    @app.get("/admin/login")
    async def login(code: str = ""):
        if _too_many_fails():
            return HTMLResponse(_message("יותר מדי ניסיונות. נסה שוב בעוד כמה דקות."), status_code=429)
        d = _load()
        h = _h256(code.strip())
        if not code or h not in d["codes"]:
            _fails.append(time.time())
            return HTMLResponse(_message("הקוד לא תקף או שפג תוקפו. צריך ליצור קוד חדש."), status_code=401)
        del d["codes"][h]
        sid = secrets.token_urlsafe(32)
        d["sessions"][_h256(sid)] = time.time() + SESSION_TTL
        _save(d)
        r = RedirectResponse("/admin", status_code=303)
        r.set_cookie(COOKIE, sid, max_age=SESSION_TTL, httponly=True, samesite="strict", path="/")
        log.info("admin login")
        return r

    @app.get("/admin")
    async def page(request: Request):
        if not _authed(request):
            return HTMLResponse(_message("צריך להתחבר: הרץ את scripts/50-open-admin.command במחשב."), status_code=401)
        return HTMLResponse(PAGE.read_text(encoding="utf-8"))

    @app.post("/admin/api/pair")
    async def pair(request: Request):
        """A 6-digit code for the iPhone app (valid 5 minutes, single use)."""
        _need(request)
        return {"code": new_code(pair=True), "ttl": 300}

    @app.get("/admin/api/whoami")
    async def whoami(request: Request):
        return {"ok": _authed(request), "name": config.NAME}

    @app.post("/admin/logout")
    async def logout(request: Request):
        sid = request.cookies.get(COOKIE)
        if sid:
            d = _load()
            d["sessions"].pop(_h256(sid), None)
            _save(d)
        r = JSONResponse({"ok": True})
        r.delete_cookie(COOKIE, path="/")
        return r

    @app.get("/admin/api/status")
    async def status(request: Request):
        _need(request)
        boards = [c for c in ctx.hub.conns if c.kind == "board"]
        dev = dict(ctx.hub.device) if boards else {}
        names = ctx.integrations.mcp_names()
        ha = "homeassistant" in names
        return {
            "device": {"online": bool(boards), **{k: dev.get(k) for k in ("fw_version", "battery", "rssi", "heap", "uptime", "device_id")}},
            "battery_estimate": ctx.battery.estimate(),
            "brain": {**await brain_status(), "model": config.CLAUDE_MODEL, "last_ok": getattr(ctx.brain, "last_ok", None)},
            "calendar": ctx.calendar.configured(),
            "home_assistant": ha,
            "composio": "composio" in names,
            "meeting_live": next(iter(ctx.meeting_mod.ACTIVE), None),
            "volume": settings().get("volume", 80),
            "server": {"uptime": int(time.time() - STARTED), "stt": config.STT_ENGINE, "voice": config.TTS_VOICE},
            "latency": ctx.last_latency,
            "state": ctx.hub.state,
            "firmware_available": (config.FIRMWARE_DIR / "firmware.bin").exists(),
        }

    @app.get("/admin/api/emotions")
    async def emotions(request: Request):
        _need(request)
        return [e for e in ctx.emotion_names()]

    @app.post("/admin/api/say")
    async def say(request: Request):
        _need(request)
        b = await request.json()
        text = str(b.get("text", ""))[:400].strip()
        if not text:
            raise HTTPException(400)
        if b.get("mode") == "ask":
            ctx.hub.run(ctx.converse(text, heard=False))    # Claude answers out loud
        else:
            ctx.hub.run(ctx.speak(text, "happy"))           # read exactly this text
        return {"ok": True}

    @app.post("/admin/api/emotion")
    async def emotion(request: Request):
        _need(request)
        b = await request.json()
        msg = {"type": "state"}
        if b.get("emotion"):
            msg["emotion"] = str(b["emotion"])[:24]
        if b.get("gesture"):
            msg["gesture"] = str(b["gesture"])[:16]
        await ctx.hub.emit(msg)
        return {"ok": True}

    @app.get("/admin/api/settings")
    async def get_settings(request: Request):
        _need(request)
        return current_settings()

    @app.post("/admin/api/settings")
    async def set_settings(request: Request):
        _need(request)
        b = await request.json()
        s = settings()
        changed = []
        for k, v in b.items():
            if k not in EDITABLE:
                continue
            attr, typ, ok = EDITABLE[k]
            try:
                if typ is bool and type(v) is not bool: raise ValueError
                v = typ(v)
                if not ok(v):
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(400, f"bad value for {k}")
            s[k] = v
            changed.append(k)
            if attr:
                setattr(config, attr, v)
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1))
        cfg = {k: s[k] for k in ("brightness", "volume", "live_transcription", "hold_to_talk", "shake_reaction", "character_sounds", "reduced_motion", "dim_seconds", "sleep_seconds") if k in changed}
        if cfg:
            await ctx.hub.emit({"type": "config", **cfg}, only_kind="board")
        if {"claude_model", "owner", "name"} & set(changed) and hasattr(ctx.brain, "reset"):
            await ctx.brain.reset()                        # persona / model are fixed when the CLI starts
        if {"lat", "lon", "city"} & set(changed):
            ctx.context.invalidate_weather()
        log.info("settings changed: %s", ", ".join(changed))
        return current_settings()

    @app.get("/admin/api/battery")
    async def battery_hist(request: Request, hours: float = 24):
        _need(request)
        cut = time.time() - hours * 3600
        return [r for r in ctx.battery._rows() if r[0] >= cut][-2000:]

    @app.get("/admin/api/meetings")
    async def meetings(request: Request):
        _need(request)
        return ctx.meeting_mod.listing()

    @app.get("/admin/api/meetings/{mid}")
    async def meeting(mid: str, request: Request):
        _need(request)
        d = ctx.meeting_mod.detail(mid)
        if d is None:
            raise HTTPException(404)
        return d

    @app.get("/admin/api/meetings/{mid}/audio")
    async def meeting_audio(mid: str, request: Request):
        _need(request)
        p = ctx.meeting_mod.audio_file(mid)
        if p is None:
            raise HTTPException(404)
        mime = "audio/mp4" if p.suffix == ".m4a" else "audio/wav"
        return FileResponse(p, media_type=mime, filename=f"meeting-{mid}{p.suffix}", content_disposition_type="inline")

    @app.delete("/admin/api/meetings/{mid}")
    async def meeting_delete(mid: str, request: Request):
        _need(request)
        if not ctx.meeting_mod.delete(mid):
            raise HTTPException(404)
        log.info("meeting %s deleted", mid)
        return {"ok": True}

    @app.get("/admin/api/last_ptt.wav")
    async def last_ptt(request: Request):
        _need(request)
        p = config.DATA_DIR / "last_ptt.wav"
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(p, media_type="audio/wav")

    @app.get("/admin/api/logs")
    async def logs(request: Request, n: int = 150):
        _need(request)
        return list(LOG_LINES)[-max(1, min(n, 400)):]

    # ---------------------------------------------------------------- show on the device
    @app.post("/admin/api/show")
    async def show(request: Request):
        _need(request)
        b = await request.json()
        return {"ok": await ctx.show_card(b, ttl=int(b.get("ttl", 15)))}

    # ---------------------------------------------------------------- Home Assistant
    @app.get("/admin/api/ha/status")
    async def ha_status(request: Request):
        _need(request)
        st = await ctx.integrations.ha_check()
        return {**st, "url": config.HA_URL, "configured": bool(ctx.integrations.ha_token()),
                "favorites": settings().get("ha_favorites", [])}

    @app.post("/admin/api/ha/token")
    async def ha_token(request: Request):
        _need(request)
        b = await request.json()
        tok = str(b.get("token", "")).strip()
        if len(tok) < 20:
            raise HTTPException(400, "token")
        st = await ctx.integrations.ha_set_token(tok)
        if st["ok"]:
            await ctx.brain.reset()                         # the CLI reads mcp.json when it starts
            await ctx.push_ha(force=True)
        return st

    @app.post("/admin/api/ha/forget")
    async def ha_forget(request: Request):
        _need(request)
        ctx.integrations.ha_forget()
        await ctx.brain.reset()
        return {"ok": True}

    @app.get("/admin/api/ha/entities")
    async def ha_entities(request: Request):
        _need(request)
        if not ctx.integrations.ha_token():
            return []
        favs = set(settings().get("ha_favorites", []))
        try:
            items = await ctx.ha.entities()
        except Exception as ex:
            raise HTTPException(502, f"Home Assistant: {type(ex).__name__}")
        for it in items:
            it["favorite"] = it["id"] in favs
        return items

    @app.post("/admin/api/ha/favorites")
    async def ha_favorites(request: Request):
        _need(request)
        b = await request.json()
        ids = [str(x)[:80] for x in b.get("ids", [])][:12]
        s = settings()
        s["ha_favorites"] = ids
        SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1))
        await ctx.push_ha(force=True)
        return {"ok": True, "ids": ids}

    @app.post("/admin/api/ha/toggle")
    async def ha_toggle(request: Request):
        _need(request)
        b = await request.json()
        try:
            new = await ctx.ha.toggle(str(b.get("id", "")))
        except Exception as ex:
            raise HTTPException(502, f"Home Assistant: {type(ex).__name__}")
        await ctx.push_ha(force=True)
        return new or {}

    @app.get("/admin/api/ha/camera/{entity}.jpg")
    async def ha_camera(entity: str, request: Request):
        _need(request)
        if not entity.startswith("camera."):
            raise HTTPException(400)
        iid = await ctx.ha.camera_image(entity)
        if not iid:
            raise HTTPException(502)
        from fastapi.responses import Response
        return Response(ctx.ha.IMAGES[iid][1], media_type="image/jpeg", headers={"cache-control": "no-store"})

    # ---------------------------------------------------------------- Gmail + Google Calendar (Composio)
    @app.get("/admin/api/composio/status")
    async def composio_status(request: Request):
        _need(request)
        return await ctx.composio.status()

    @app.post("/admin/api/composio/key")
    async def composio_key(request: Request):
        _need(request)
        b = await request.json()
        st = await ctx.composio.set_key(str(b.get("key", "")).strip())
        return st

    @app.post("/admin/api/composio/connect")
    async def composio_connect(request: Request):
        _need(request)
        b = await request.json()
        return await ctx.composio.connect(str(b.get("toolkit", "")))

    @app.post("/admin/api/composio/disconnect")
    async def composio_disconnect(request: Request):
        _need(request)
        b = await request.json()
        r = await ctx.composio.disconnect(str(b.get("toolkit", "")))
        ctx.integrations.write_mcp()
        await ctx.brain.reset()
        return r

    @app.post("/admin/api/composio/refresh")
    async def composio_refresh(request: Request):
        """After the Google approval: rebuild Claude's tools so it can use the new connection."""
        _need(request)
        st = await ctx.composio.status()
        ctx.integrations.write_mcp()
        await ctx.brain.reset()
        return st

    @app.post("/admin/api/ota")
    async def ota(request: Request):
        _need(request)
        if not (config.FIRMWARE_DIR / "firmware.bin").exists():
            raise HTTPException(404, "no firmware")
        base = f"http://{config.LAN_IP}:{config.PORT}"
        await ctx.hub.emit({"type": "ota", "url": f"{base}/fw/firmware.bin?token={config.DEVICE_TOKEN}"}, only_kind="board")
        log.info("OTA requested from the admin page")
        return {"ok": True}

    @app.post("/admin/api/brain/reset")
    async def brain_reset(request: Request):
        _need(request)
        await ctx.brain.reset()
        return {"ok": True}


def _message(text: str) -> str:
    return ("<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<body style='background:#0b0f12;color:#e6eef2;font:18px system-ui;display:grid;place-items:center;height:100vh;margin:0'>"
            f"<div style='max-width:420px;padding:24px;text-align:center'>{text}</div></body></html>")
