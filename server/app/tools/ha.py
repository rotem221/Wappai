"""Home Assistant over its REST API: favourite devices for the board's Home page, toggling, camera snapshots.

Voice control itself goes through Claude with Home Assistant's MCP server (see scripts/13-home-assistant.command);
this module is what the board's buttons, the admin page and the on-screen cards use.

Token: CLAUDE_WORKDIR/ha_token (chmod 600, written by script 13) or HA_TOKEN in the environment.
"""
import asyncio
import io
import logging
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger("ha")
TOKEN_FILE = Path(config.CLAUDE_WORKDIR) / "ha_token"
TOGGLABLE = ("light", "switch", "fan", "input_boolean", "cover", "lock", "scene", "script", "media_player", "climate",
             "automation", "vacuum")
IMAGES: dict[str, tuple[float, bytes]] = {}          # id -> (time, jpeg) for the board to download


def token() -> str:
    if config.HA_TOKEN:
        return config.HA_TOKEN
    try:
        return TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def configured() -> bool:
    return bool(token())


def _h():
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


async def _get(path: str, timeout=8):
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(f"{config.HA_URL}{path}", headers=_h())
        r.raise_for_status()
        return r


async def states() -> list[dict]:
    return (await _get("/api/states")).json()


async def state(entity: str) -> dict | None:
    try:
        return (await _get(f"/api/states/{entity}")).json()
    except Exception:
        return None


def _name(s: dict) -> str:
    return s.get("attributes", {}).get("friendly_name") or s["entity_id"].split(".", 1)[1]


def summarize(s: dict) -> dict:
    """Compact form for the board / admin: id, name, kind, on, state text."""
    dom = s["entity_id"].split(".")[0]
    st = s.get("state", "")
    on = st in ("on", "open", "opening", "unlocked", "playing", "heat", "cool", "heat_cool", "auto", "cleaning")
    text = {"on": "פועל", "off": "כבוי", "open": "פתוח", "closed": "סגור", "locked": "נעול", "unlocked": "לא נעול",
            "unavailable": "לא זמין", "playing": "מנגן", "paused": "מושהה", "idle": "ממתין"}.get(st, st)
    if dom == "climate":
        t = s.get("attributes", {}).get("current_temperature")
        if t is not None:
            text = f"{text} · {t}°"
    if dom in ("sensor",):
        u = s.get("attributes", {}).get("unit_of_measurement", "")
        text = f"{st}{u}"
    return {"id": s["entity_id"], "name": _name(s), "kind": dom, "on": on, "state": text,
            "available": st != "unavailable"}


async def entities() -> list[dict]:
    """Everything worth showing in the admin picker (controllable devices, cameras, a few sensors)."""
    out = []
    for s in await states():
        dom = s["entity_id"].split(".")[0]
        if dom in TOGGLABLE or dom in ("camera", "sensor", "binary_sensor"):
            out.append(summarize(s))
    return sorted(out, key=lambda x: (x["kind"], x["name"]))


async def favorites(ids: list[str]) -> list[dict]:
    """The board's Home page: the chosen favourites, or (none chosen) the first lights / switches / covers."""
    all_ = {s["entity_id"]: s for s in await states()}
    if not ids:
        ids = [e for e, s in all_.items() if e.split(".")[0] in ("light", "switch", "cover", "fan", "lock")
               and s.get("state") != "unavailable"][:8]
    return [summarize(all_[e]) for e in ids if e in all_][:12]


async def toggle(entity: str) -> dict | None:
    dom = entity.split(".")[0]
    cur = await state(entity)
    if not cur:
        return None
    st = cur.get("state")
    if dom in ("scene", "script"):
        svc = (dom, "turn_on")
    elif dom == "lock":
        svc = ("lock", "unlock" if st == "locked" else "lock")
    elif dom == "cover":
        svc = ("cover", "close_cover" if st in ("open", "opening") else "open_cover")
    elif dom == "media_player":
        svc = ("media_player", "media_play_pause")
    elif dom == "vacuum":
        svc = ("vacuum", "return_to_base" if st == "cleaning" else "start")
    elif dom == "climate":
        svc = ("climate", "turn_off" if st not in ("off", "unavailable") else "turn_on")
    else:
        svc = ("homeassistant", "toggle")
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.post(f"{config.HA_URL}/api/services/{svc[0]}/{svc[1]}", headers=_h(), json={"entity_id": entity})
        r.raise_for_status()
    await asyncio.sleep(0.6)                     # let the device report its new state
    new = await state(entity)
    log.info("toggle %s via %s.%s -> %s", entity, svc[0], svc[1], new.get("state") if new else "?")
    return summarize(new) if new else None


def _fit_jpeg(data: bytes, size: int = 416) -> bytes:
    """Centre-crop to a square and scale for the round screen (baseline JPEG: what the board's decoder reads)."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((size, size))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80, progressive=False)
        return out.getvalue()
    except ImportError:
        p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-vf",
                            f"crop='min(iw,ih)':'min(iw,ih)',scale={size}:{size}", "-q:v", "5", "-f", "mjpeg", "pipe:1"],
                           input=data, capture_output=True, timeout=10)
        return p.stdout


async def camera_image(entity: str) -> str | None:
    """Snapshot -> stored JPEG id (served at /img/<id>.jpg)."""
    try:
        r = await _get(f"/api/camera_proxy/{entity}", timeout=12)
    except Exception as e:
        log.warning("camera %s: %s", entity, type(e).__name__)
        return None
    jpg = await asyncio.to_thread(_fit_jpeg, r.content)
    if not jpg:
        return None
    now = time.time()
    for k in [k for k, (t, _) in IMAGES.items() if now - t > 300]:
        del IMAGES[k]
    iid = uuid.uuid4().hex[:10]
    IMAGES[iid] = (now, jpg)
    return iid


async def cameras() -> list[dict]:
    return [summarize(s) for s in await states() if s["entity_id"].startswith("camera.")]
