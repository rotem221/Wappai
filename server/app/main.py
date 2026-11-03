"""Companion brain server.

  /ws            WebSocket for the board (and the web simulator): JSON control + binary PCM 16 kHz mono
  /              Wappai web chat (same-origin cookie session)
  /simulator     developer face preview, needs ?token=
  /api/*         health, test hooks (emotion, say), OTA trigger
  /fw/<file>     firmware images for OTA

Protocol: docs/PROTOCOL.md
"""
import re
import asyncio
import json
import logging
import secrets
import time
import uuid
from contextvars import ContextVar
TURN_GENERATION=ContextVar("wappai_turn",default=None)

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from types import SimpleNamespace

from . import admin, config, wappai, web_auth
from .brain.persona import emotion_names
from .brain.reply import ReplyParser
from . import integrations
from .tools import battery, calendar, composio, context, ha, meeting as meeting_mod
from .voice import adpcm, stt, stt_stream, tts

USE_STREAM = config.STT_ENGINE in ("stream","hybrid") and stt_stream.available()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("companion")

if config.BRAIN == "api" and config.ANTHROPIC_API_KEY:
    from .brain.api import AnthropicAPI as Brain
else:
    from .brain.claude_cli import ClaudeCLI as Brain

app = FastAPI(title="Wappai")
brain = Brain()
try:
    from .brain.claude_cli import oneshot as _oneshot
except Exception:                              # pragma: no cover
    _oneshot = None
EMOTIONS = set(emotion_names())
FRAME = 2048          # bytes of PCM per binary frame
LAST_LATENCY: dict = {}   # timeline of the last spoken answer (shown in the admin page)


class Conn:
    def __init__(self, ws: WebSocket, kind: str):
        self.ws, self.kind = ws, kind
        self.info: dict = {}
        self.lock = asyncio.Lock()

    async def send(self, obj=None, binary: bytes | None = None):
        async with self.lock:
            if binary is not None:
                await self.ws.send_bytes(binary)
            else:
                await self.ws.send_text(json.dumps(obj, ensure_ascii=False))


class Hub:
    def __init__(self):
        self.receipts={}
        self.generation=0
        self.conns: set[Conn] = set()
        self.task: asyncio.Task | None = None
        self.state = {"emotion": "idle"}
        self.device: dict = {}

    async def emit(self, obj=None, binary=None, only_kind=None):
        generation=TURN_GENERATION.get()
        if generation is not None and generation!=self.generation: return
        if obj is not None: await wappai.observe(obj)
        dead = []
        for c in list(self.conns):
            if only_kind and c.kind != only_kind:
                continue
            try:
                await c.send(obj, binary)
            except Exception:
                dead.append(c)
        for c in dead:
            self.conns.discard(c)

    async def set_state(self, **kw):
        self.state.update({k: v for k, v in kw.items() if k in ("emotion",)})
        await self.emit({"type": "state", **kw})

    def interrupt(self):
        if self.task and not self.task.done():
            self.task.cancel()

    def run(self, coro):
        self.interrupt()
        self.generation+=1
        generation=self.generation
        async def scoped():
            token=TURN_GENERATION.set(generation)
            try: return await coro
            finally: TURN_GENERATION.reset(token)
        self.task = asyncio.create_task(scoped())


hub = Hub()


# ---------------------------------------------------------------- on-screen cards
TIME_WORDS = ("השעה", "מה השעה", "שעה עכשיו", "תאריך", "איזה יום", "מה היום", "באיזה יום")
from .display_intent import weather_requested, home_requested, requested_device


async def device_badge(entity: str, pending=False):
    if not ha.configured() or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", entity or ""):
        return False
    st = await ha.state(entity)
    if not st: return False
    await hub.emit({"type":"device.badge","dev":ha.summarize(st),"pending":pending,"ttl":60 if pending else 12})
    return True


async def show_card(attrs: dict, ttl: int = 12) -> bool:
    """Shows information on the board's screen: time, weather, timer, text, camera, device."""
    what = (attrs.get("what") or attrs.get("type") or "").strip()
    card: dict = {}
    if what in ("time", "date", "clock"):
        card = {"kind": "time", "date": context.date_he()}
    elif what == "weather":
        await context.weather()
        card = {"kind": "weather", **context.weather_data()}
    elif what == "timer":
        card = {"kind": "timer"}
    elif what == "text":
        card = {"kind": "text", "title": str(attrs.get("title", ""))[:60], "body": str(attrs.get("body", ""))[:300]}
    elif what in ("camera", "image") and ha.configured():
        ent = attrs.get("entity", "")
        if not ent:
            cams = await ha.cameras()
            ent = cams[0]["id"] if cams else ""
        iid = await ha.camera_image(ent) if ent else None
        if iid:
            st = await ha.state(ent)
            card = {"kind": "image", "url": f"/img/{iid}.jpg", "title": ha.summarize(st)["name"] if st else ""}
            ttl = max(ttl, 20)
    elif what == "device" and ha.configured():
        st = await ha.state(attrs.get("entity", ""))
        if st:
            card = {"kind": "device", "dev": ha.summarize(st)}
    if not card:
        return False
    await hub.emit({"type": "card", "ttl": ttl, **card}, only_kind="board")
    log.info("card %s", card.get("kind"))
    return True


async def converse(text: str, heard: bool = True, on_done=None, t0: float | None = None):
    utt = uuid.uuid4().hex[:8]
    t0 = t0 or time.time()
    marks: dict[str, float] = {}              # latency timeline of this turn, logged once the first audio is out
    try:
        if heard:
            await hub.emit({"type": "heard", "text": text})
        smart_home = home_requested(text)
        target = None
        await hub.emit({"type":"interaction","text":"בודק את הבקשה…" if smart_home else "חושב…","clear_card":True})
        if smart_home and ha.configured():
            try:
                target = requested_device(text, await asyncio.wait_for(ha.entities(),2))
            except Exception:
                log.info("Home display lookup unavailable")
        if target:
            await hub.emit({"type":"device.badge","dev":target,"pending":True,"ttl":60})
        ctx = await context.build(hub.device, text)
        if smart_home:
            ctx += '\nתצוגה: זו בקשת בית חכם. אין להציג מזג אוויר בגלל המילה מזגן או מעלות. אחרי בדיקת תוצאת הפעולה בכלים, שלח <show what="device" entity="הישות המדויקת"/> לתצוגת חיווי קטן. אל תטען להצלחה ללא תוצאת כלי.'
        ctx += "\n" + wappai.conversation_context(text)
        parser = ReplyParser(EMOTIONS)
        q: asyncio.Queue = asyncio.Queue(maxsize=16)
        emotion = {"v": "speaking"}
        flags = {"meeting": False}
        spoken: list[str] = []

        # Each sentence starts synthesizing as soon as it is complete (in parallel); the speaker plays them
        # in order and streams audio while it is still being generated.
        async def produce(sentence: str, out: asyncio.Queue, emo: str | None = None):
            try:
                async for chunk in tts.stream(sentence, emo):
                    await out.put(chunk)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                await out.put(error)
            else:
                await out.put(None)

        async def speaker():
            seq = 0
            while True:
                item = await q.get()
                if item is None:
                    break
                sent, emo, chunks = item
                await hub.emit({"type": "say", "id": utt, "seq": seq, "text": sent, "emotion": emo, "audio": True})
                pending = b""
                while (c := await chunks.get()) is not None:
                    if isinstance(c,Exception):raise c
                    if "audio" not in marks:
                        marks["audio"] = time.time() - t0
                        log.info("latency: %s", " ".join(f"{k} {v:.2f}s" for k, v in marks.items()))
                        LAST_LATENCY.clear(); LAST_LATENCY.update({k: round(v, 2) for k, v in marks.items()}, at=int(time.time()))
                    pending += c
                    while len(pending) >= FRAME:
                        await hub.emit(binary=pending[:FRAME])
                        pending = pending[FRAME:]
                if pending:
                    await hub.emit(binary=pending)
                await hub.emit({"type": "audio_end", "id": utt, "seq": seq, "final": False})
                seq += 1
            await hub.emit({"type": "audio_end", "id": utt, "seq": seq, "final": True})

        producers: list[asyncio.Task] = []
        sp = asyncio.create_task(speaker())

        async def handle(evs):
            for e in evs:
                if e.kind == "emotion":
                    emotion["v"] = e.value
                    await hub.set_state(emotion=e.value)
                elif e.kind == "gesture":
                    await hub.emit({"type": "state", "gesture": e.attrs.get("name", "nod")})
                elif e.kind == "timer":
                    try:
                        secs = int(float(e.attrs.get("seconds", "0")))
                    except ValueError:
                        secs = 0
                    if secs > 0:
                        if secs>86400 or not _boards(): raise RuntimeError("Timer cannot be applied: device offline or invalid duration")
                        command_id=uuid.uuid4().hex
                        receipt=asyncio.get_running_loop().create_future();hub.receipts[command_id]=receipt
                        try:
                            await hub.emit({"type":"timer","id":command_id,"seconds":secs,"label":e.attrs.get("label","")},only_kind="board")
                            result=await asyncio.wait_for(receipt,5)
                            if result.get("status")!="applied":raise RuntimeError("Device rejected timer")
                        finally:hub.receipts.pop(command_id,None)
                        await hub.emit({"type": "card", "kind": "timer", "ttl": 6}, only_kind="board")
                elif e.kind == "timer_cancel":
                    await hub.emit({"type": "timer_cancel"})
                elif e.kind == "meeting_start":
                    flags["meeting"] = True
                elif e.kind == "show":
                    w = e.attrs.get("what", "")
                    if w == "weather" and smart_home and not weather_requested(text):
                        continue
                    if w == "device":
                        await device_badge(e.attrs.get("entity", ""))
                    elif w not in shown:
                        shown.add(w)
                        await show_card(e.attrs)
                elif e.kind == "sentence":
                    marks.setdefault("first_sentence", time.time() - t0)
                    spoken.append(e.value)
                    chunks: asyncio.Queue = asyncio.Queue(maxsize=24)
                    producers.append(asyncio.create_task(produce(e.value, chunks, emotion["v"])))
                    await q.put((e.value, emotion["v"], chunks))

        # questions about the time or the weather show their card right away, while Claude is still thinking
        shown: set = set()
        if any(w in text for w in TIME_WORDS) and await show_card({"what": "time"}):
            shown.add("time")
        if weather_requested(text) and await show_card({"what": "weather"}, ttl=16):
            shown.add("weather")
        marks["context"] = time.time() - t0
        async for chunk in wappai.current_brain().ask(text, ctx):
            marks.setdefault("first_token", time.time() - t0)
            await handle(parser.feed(chunk))
        await handle(parser.finish())
        if target: await device_badge(target['id'])
        await q.put(None)
        await sp
        if flags["meeting"]:                      # only after the confirmation was spoken (mic must not hear it)
            await asyncio.sleep(0.6)
            await hub.emit({"type": "record", "mode": "meeting"})
        await hub.emit({"type":"turn.completed"})
        if on_done:
            on_done(" ".join(spoken))
    except asyncio.CancelledError:
        pending=locals().get("producers", []) + ([locals()["sp"]] if "sp" in locals() else [])
        for p in pending:
            p.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        await hub.emit({"type": "stop"})
        raise
    except Exception as ex:
        pending=locals().get("producers", []) + ([locals()["sp"]] if "sp" in locals() else [])
        for task in pending: task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
        log.exception("conversation failed")
        await hub.emit({"type":"turn.failed"})
        await hub.set_state(emotion="error")
        await hub.emit({"type": "say", "id": utt, "seq": 0, "text": "משהו השתבש אצלי. נסה שוב עוד רגע.", "emotion": "error",
                        "audio": False})


def _save_last(pcm: bytes) -> tuple[float, float]:
    """Keeps the last push-to-talk recording (data/last_ptt.wav) for debugging and returns (rms, peak) 0..1."""
    import array, math, wave
    a = array.array("h", pcm[: len(pcm) // 2 * 2])
    rms = math.sqrt(sum(x * x for x in a) / len(a)) / 32768 if a else 0.0
    peak = max((abs(x) for x in a), default=0) / 32768
    try:
        if not config.RETAIN_DEBUG_AUDIO: return rms, peak
        with wave.open(str(config.DATA_DIR / "last_ptt.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
    except OSError:
        pass
    return rms, peak


async def _hint(text: str, emotion: str = "confused"):
    await hub.set_state(emotion=emotion, gesture="shake", ring="none")
    await hub.emit({"type": "say", "id": uuid.uuid4().hex[:8], "seq": 0, "text": text, "emotion": emotion, "audio": False})


async def handle_audio(pcm: bytes, sess=None):
    t0 = time.time()                          # button released
    secs = len(pcm) / 32000
    rms, peak = await asyncio.to_thread(_save_last, pcm)
    log.info("ptt audio %.1fs rms %.4f peak %.3f", secs, rms, peak)
    if secs < 0.5:
        if sess is not None:
            sess.cancel()
        await _hint("החזק את BOOT בזמן הדיבור ושחרר בסיום" if admin.current_settings()["hold_to_talk"] else "לחץ BOOT, דבר, ואז לחץ שוב לסיום")
        return
    await hub.set_state(emotion="thinking", ring="think")
    text = ""
    if sess is not None:
        text = await sess.finish()
    if config.STT_ENGINE == "hybrid":
        from .voice import stt_fast
        language, multilingual = await stt_fast.recognize(pcm)
        if language == "en": text = multilingual
    if len(text) < 2:
        text = await stt.transcribe(pcm)
    if not text:
        await _hint("לא שמעתי טוב. נסה שוב, קצת יותר קרוב" if peak > 0.01 else "לא שמעתי כלום. המיקרופון שקט")
        return
    log.info("latency: stt %.2fs", time.time() - t0)
    await converse(text, t0=t0)


async def _meeting_title(mt):
    await hub.emit({"type": "meeting", "id": mt.id, "title": mt.meta["title"]}, only_kind="board")


def new_meeting(resume: str | None = None):
    """Start (or continue after a dropped connection) a meeting recording."""
    if resume and resume in meeting_mod.ACTIVE:
        mt = meeting_mod.ACTIVE[resume]
        mt.detached_at = 0
        log.info("meeting %s: board is back", mt.id)
        return mt
    return meeting_mod.Meeting(resume or None, on_title=_meeting_title, oneshot=_oneshot)


async def _expire_meeting(mt):
    """Board gone mid-meeting: give it RESUME_S to come back, then close the meeting with what we have."""
    await asyncio.sleep(meeting_mod.RESUME_S)
    if mt.detached_at and mt.id in meeting_mod.ACTIVE:
        log.info("meeting %s: board did not come back, closing", mt.id)
        await handle_meeting(mt)


async def handle_meeting(mt):
    await hub.set_state(emotion="working", ring="think")
    text, md = await mt.finish()
    if len(text) < 10:
        await hub.set_state(emotion="confused", ring="none")
        await hub.emit({"type": "say", "id": uuid.uuid4().hex[:8], "seq": 0, "text": "לא הצלחתי לשמוע את הפגישה.",
                        "emotion": "confused", "audio": False})
        return
    src = mt.summary_source()
    title = mt.meta.get("title") or ""
    written = ""
    if _oneshot:
        written = await _oneshot(
            "זה תמלול אוטומטי (עם טעויות זיהוי) של פגישה" + (f" בנושא \"{title}\"" if title else "") +
            f", באורך {mt.meta['seconds'] / 60:.0f} דקות. כתוב סיכום מסודר בעברית ב-Markdown עם הכותרות: "
            "## תקציר (2-3 משפטים), ## נקודות עיקריות, ## החלטות, ## משימות (מי, מה, עד מתי). "
            "אם משהו לא הוזכר כתוב 'לא הוזכר'. בלי להעיר על איכות התמלול.\n\n" + src, "sonnet", timeout=300)
    if written:
        mt.set_summary(written)
        prompt = ("סיימתי לתמלל פגישה" + (f" בנושא \"{title}\"" if title else "") + ". זה הסיכום הכתוב שלה:\n" + written[:6000] +
                  "\n\nתגיד בקול סיכום קצר של שניים-שלושה משפטים: על מה דיברו ומה הוחלט, ותגיד שהסיכום המלא וההקלטה נמצאים בפאנל.")
        await converse(prompt, heard=False)
        return
    prompt = ("זה תמלול אוטומטי (עם טעויות זיהוי) של פגישה שהקלטתי. תן סיכום קולי קצר של שניים עד ארבעה משפטים: "
              "על מה דיברו, מה הוחלט, ומי עושה מה ועד מתי. בלי לחזור על אותו דבר פעמיים ובלי להעיר על איכות התמלול. התמלול:\n"
              + src)
    def done(summary: str):
        mt.set_summary(summary if getattr(brain, "last_ok", True) else
                       "(לא נוצר סיכום: המוח של Claude לא היה זמין. התמלול וההקלטה נשמרו.)")
    await converse(prompt, heard=False, on_done=done)


def _auth(token: str | None):
    if not config.DEVICE_TOKEN:
        return False
    return token is not None and secrets.compare_digest(token, config.DEVICE_TOKEN)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    token = ws.query_params.get("token")
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    kind = ws.query_params.get("kind", "board")
    browser = kind=="web" and web_auth.same_origin(ws) and web_auth.authorized(ws,wappai.store)
    if not _auth(token) and not browser:
        await ws.close(code=4401)
        return
    await ws.accept()
    conn = Conn(ws, kind)
    hub.conns.add(conn)
    log.info("%s connected (%d total)", conn.kind, len(hub.conns))
    rec: bytearray | None = None
    sess = None
    mt = None
    mt_codec = ""
    try:
        await conn.send({"type": "ping", "t": int(time.time())})
        await conn.send({"type": "state", **hub.state})
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if mt is not None:
                    mt.feed(adpcm.decode(msg["bytes"]) if mt_codec == "adpcm" else msg["bytes"])
                elif rec is not None:
                    if len(msg["bytes"])>4096 or len(rec)+len(msg["bytes"])>16000*2*120:
                        await ws.close(code=1009); break
                    rec += msg["bytes"]
                    if sess is not None:
                        sess.feed(msg["bytes"])
                continue
            if len(msg.get("text") or "")>16384: await ws.close(code=1009); break
            data = json.loads(msg.get("text") or "{}")
            t = data.get("type")
            if t == "hello":
                conn.info = data
                if conn.kind == "board":
                    hub.device = data
                    asyncio.create_task(wappai.studio.restore())
                    await wappai.emit({"type":"device.connection","online":True})
                    battery.record(data.get("battery"))
                    st_ = admin.settings()
                    cfg = {k: st_[k] for k in ("brightness", "volume", "live_transcription", "hold_to_talk", "shake_reaction", "character_sounds", "reduced_motion", "dim_seconds", "sleep_seconds") if k in st_}
                    if cfg:
                        await conn.send({"type": "config", **cfg})
                    asyncio.create_task(push_info())
                    asyncio.create_task(push_ha(force=True))
                log.info("hello %s", data)
            elif t == "command.result" and conn.kind == "board":
                receipt=hub.receipts.get(data.get("id"))
                if receipt and not receipt.done():receipt.set_result(data)
                await hub.emit(data,only_kind="sim")
            elif t == "status":
                if conn.kind == "board":
                    hub.device.update({k: v for k, v in data.items() if k != "type"})
                    battery.record(data.get("battery"))
                await hub.emit(data, only_kind="sim")
            elif t == "ptt_start" and data.get("mode") == "meeting":
                hub.interrupt()
                resume = str(data.get("resume") or "")
                if mt is not None and mt.id != resume:
                    m_, mt = mt, None
                    hub.run(handle_meeting(m_))
                mt = new_meeting(resume)
                mt_codec = str(data.get("codec") or "")
                await conn.send({"type": "meeting", "id": mt.id, "title": mt.meta.get("title", "")})
                await hub.emit({"type": "state", "emotion": "listening", "ring": "rec"}, only_kind="sim")
            elif t == "ptt_end" and mt is not None:
                m_, mt = mt, None
                hub.run(handle_meeting(m_))
            elif t == "ptt_start":
                hub.interrupt()
                rec = bytearray()
                if sess is not None:
                    sess.cancel()
                capture_id = uuid.uuid4().hex
                async def partial_text(text, cid=capture_id):
                    if cid == capture_id and admin.current_settings()["live_transcription"]:
                        await hub.emit({"type":"transcript.partial","capture_id":cid,"text":text[-150:]})
                sess = stt_stream.Session(on_partial=partial_text) if USE_STREAM else None
                await hub.emit({"type":"transcript.partial","capture_id":capture_id,"text":""})
                await hub.emit({"type": "state", "emotion": "listening", "ring": "rec"}, only_kind="sim")
            elif t == "ptt_end":
                capture_id = ""
                await hub.emit({"type":"transcript.partial","text":""})
                pcm, rec = bytes(rec or b""), None
                hub.run(handle_audio(pcm, sess))
                sess = None
            elif t == "text":               # typed message (simulator / tests)
                hub.run(converse(str(data.get("text", ""))[:500], heard=False))
            elif t == "ha_toggle" and ha.configured():
                async def _tog(ent=str(data.get("id", ""))):
                    try:
                        new = await ha.toggle(ent)
                    except Exception as ex:
                        log.warning("ha toggle failed: %s", ex)
                        new = None
                    if new is not None:
                        await hub.emit({"type": "ha_state", "item": new}, only_kind="board")
                    await push_ha(force=True)
                    if new is None:
                        await hub.emit({"type": "toast", "text": "לא הצלחתי לשנות את המכשיר"}, only_kind="board")
                asyncio.create_task(_tog())
            elif t == "setting":
                s_ = admin.settings()
                if isinstance(data.get("brightness"), int):
                    s_["brightness"] = max(20, min(255, data["brightness"]))
                if isinstance(data.get("volume"), int):
                    s_["volume"] = max(0, min(100, data["volume"]))
                admin.SETTINGS_FILE.write_text(json.dumps(s_, ensure_ascii=False, indent=1))
            elif t == "pip.selected" and conn.kind == "board":
                await hub.emit(data, only_kind="sim")
            elif t == "touch":
                await hub.emit(data, only_kind="sim")
            elif t == "event":
                log.info("device event %s", data)
            elif t == "pong":
                pass
    except WebSocketDisconnect:
        pass
    finally:
        capture_id = ""
        if sess is not None: sess.cancel()
        if conn.kind=="board": await hub.emit({"type":"transcript.partial","text":""})
        if mt is not None:                 # connection lost mid-meeting: wait for the board to come back
            mt.detach()
            asyncio.create_task(_expire_meeting(mt))
        hub.conns.discard(conn)
        if conn.kind=="board": await wappai.emit({"type":"device.connection","online":any(c.kind=="board" for c in hub.conns)})
        log.info("%s disconnected", conn.kind)


async def pinger():
    while True:
        await asyncio.sleep(30)
        await hub.emit({"type": "ping", "t": int(time.time())})


def _boards() -> bool:
    return any(c.kind == "board" for c in hub.conns)


async def push_info():
    """Clock page data for the board: Hebrew date and the weather."""
    await context.weather()
    await hub.emit({"type": "info", "date": context.date_he(), "weather": context.weather_data()}, only_kind="board")


_last_ha: dict = {"items": None}


async def push_ha(force: bool = False):
    if not ha.configured() or not _boards():
        return
    try:
        items = await ha.favorites(admin.settings().get("ha_favorites", []))
    except Exception as ex:
        log.debug("ha poll: %s", ex)
        return
    if force or items != _last_ha["items"]:
        _last_ha["items"] = items
        await hub.emit({"type": "ha_list", "items": items}, only_kind="board")


async def info_loop():
    n = 0
    while True:
        await asyncio.sleep(5)
        n += 1
        if _boards():
            await push_ha()
            if n % 120 == 0:              # every 10 minutes
                await push_info()


@app.on_event("startup")
async def startup():
    asyncio.create_task(pinger())
    asyncio.create_task(info_loop())
    await asyncio.to_thread(meeting_mod.recover)
    integrations.startup()
    asyncio.create_task(stt_stream.warmup() if USE_STREAM else stt.warmup())
    if config.STT_ENGINE == "hybrid":
        from .voice import stt_fast
        asyncio.create_task(stt_fast.warmup())


def _check(request: Request):
    tok = request.query_params.get("token") or request.headers.get("authorization", "")[7:]
    if not _auth(tok):
        raise HTTPException(401)


@app.get("/api/health")
async def health():
    return {"ok": True, "devices": [c.info for c in hub.conns if c.kind == "board"], "brain": await brain.status(),
            "battery_estimate": battery.estimate(), "calendar": calendar.configured(),
            "state": hub.state}


@app.post("/api/emotion")
async def api_emotion(request: Request, name: str, gesture: str = ""):
    _check(request)
    await hub.emit({"type": "state", "emotion": name, **({"gesture": gesture} if gesture else {})})
    return {"ok": True}


async def speak(text: str, emo: str = "speaking"):
    """Says exactly `text` on the device (no brain)."""
    utt = uuid.uuid4().hex[:8]
    await hub.set_state(emotion=emo)
    await hub.emit({"type": "say", "id": utt, "seq": 0, "text": text, "emotion": emo, "audio": True})
    pending = b""
    async for c in tts.stream(text, emo):
        pending += c
        while len(pending) >= FRAME:
            await hub.emit(binary=pending[:FRAME])
            pending = pending[FRAME:]
    if pending:
        await hub.emit(binary=pending)
    await hub.emit({"type": "audio_end", "id": utt, "seq": 0, "final": True})


@app.post("/api/say")
async def api_say(request: Request):
    """Make the creature speak (e.g. from Home Assistant). Body: {"text": "...", "emotion": "happy"}"""
    _check(request)
    body = await request.json()
    text, emo = str(body.get("text", ""))[:400], body.get("emotion", "speaking")
    hub.run(speak(text, emo))
    return {"ok": True}


@app.post("/api/show")
async def api_show(request: Request):
    """Show a card on the board. Body: {"what": "time|weather|timer|text|camera|device", "title", "body", "entity", "ttl"}"""
    _check(request)
    body = await request.json()
    ok = await show_card(body, ttl=int(body.get("ttl", 12)))
    return {"ok": ok}


@app.post("/api/push")
async def api_push(request: Request):
    """Re-send the clock-page info and the Home page list to the board (tests)."""
    _check(request)
    await push_info()
    await push_ha(force=True)
    return {"ok": True, "ha": ha.configured()}


@app.post("/api/ask")
async def api_ask(request: Request):
    """Typed question; the answer is spoken on the device. Body: {"text": "..."}"""
    _check(request)
    body = await request.json()
    hub.run(converse(str(body.get("text", ""))[:500], heard=False))
    return {"ok": True}


@app.get("/api/meetings")
async def api_meetings(request: Request):
    _check(request)
    return meeting_mod.listing()


@app.get("/api/meetings/{mid}")
async def api_meeting(mid: str, request: Request):
    _check(request)
    d = meeting_mod.detail(mid)
    if d is None:
        raise HTTPException(404)
    return d


@app.post("/api/ota")
async def api_ota(request: Request, file: str = "firmware.bin"):
    _check(request)
    if not (config.FIRMWARE_DIR / file).exists():
        raise HTTPException(404, "no firmware")
    base = request.query_params.get("base") or config.PUBLIC_URL or f"http://{config.LAN_IP}:{config.PORT}"
    url = f"{base}/fw/{file}?token={config.DEVICE_TOKEN}"
    await hub.emit({"type": "ota", "url": url}, only_kind="board")
    return {"ok": True, "url": url}


@app.get("/fw/{name}")
async def fw(name: str, request: Request):
    _check(request)
    p = (config.FIRMWARE_DIR / name).resolve()
    if config.FIRMWARE_DIR.resolve() not in p.parents or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/octet-stream")


@app.get("/img/{iid}.jpg")
async def img(iid: str, request: Request):
    _check(request)
    it = ha.IMAGES.get(iid)
    if not it:
        raise HTTPException(404)
    from fastapi.responses import Response
    return Response(it[1], media_type="image/jpeg")


SIM = config.ROOT / "sim"


@app.get("/")
async def sim_index():
    return HTMLResponse((SIM / "index.html").read_text(encoding="utf-8"),headers={"Cache-Control":"no-cache"})


@app.get("/simulator")
async def legacy_simulator():
    return HTMLResponse((SIM / "simulator.html").read_text(encoding="utf-8"))


@app.get("/sim/{name}")
async def sim_file(name: str):
    p = (SIM / name).resolve()
    if SIM.resolve() not in p.parents or not p.exists():
        raise HTTPException(404)
    return FileResponse(p,headers={"Cache-Control":"no-cache"} if p.suffix in (".js",".css") else None)


admin.register(app, SimpleNamespace(hub=hub, brain=brain, converse=converse, speak=speak, emotion_names=emotion_names,
                                    battery=battery, calendar=calendar, context=context, meeting_mod=meeting_mod,
                                    last_latency=LAST_LATENCY, ha=ha, show_card=show_card, push_ha=push_ha,
                                    integrations=integrations, composio=composio))


wappai.register(app, SimpleNamespace(hub=hub,converse=converse))
