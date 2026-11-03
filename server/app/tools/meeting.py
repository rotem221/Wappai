"""Meeting transcription for meetings of any length (tested for hours).

The board streams the mic; nothing big is kept in memory:
  - audio goes to disk in 5-minute parts (WAV while recording, then AAC .m4a, ~15 MB per hour);
  - speech is transcribed live, sentence by sentence (streaming STT cut at pauses), into transcript.txt;
  - after a few minutes a short title is generated and shown on the board;
  - every ~6000 characters of transcript a partial summary is written, so the final summary of a 4-hour meeting
    is built from those instead of one huge prompt.

Files: DATA_DIR/meetings/<id>/ meta.json, transcript.txt, part-NNN.m4a, audio.m4a (all parts, made at the end),
summary.md. Older meetings (flat <id>.md / <id>.wav files) are still listed.

If the board's connection drops, the meeting waits (RESUME_S) for it to come back and continue; the board buffers
the audio meanwhile.
"""
import asyncio
import json
import logging
import shutil
import subprocess
import time
import wave
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import config
from ..voice import stt_stream

log = logging.getLogger("meeting")
DIR = config.DATA_DIR / "meetings"
DIR.mkdir(parents=True, exist_ok=True)
PART_S = 300                     # seconds of audio per part file
RESUME_S = 600                   # a dropped board may come back within this time and continue the meeting
CHUNK_CHARS = 6000               # partial summary every this many transcript characters
ACTIVE: dict[str, "Meeting"] = {}


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def _encode(wav: Path) -> Path | None:
    """WAV part -> AAC (plays everywhere, including iPhone Safari). Keeps the WAV if ffmpeg fails."""
    out = wav.with_suffix(".m4a")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "32k", str(out)],
                       check=True, timeout=600)
        wav.unlink()
        return out
    except Exception as e:
        log.warning("encode %s failed: %s", wav.name, e)
        return None


def _concat(d: Path) -> Path | None:
    parts = sorted(d.glob("part-*.m4a"))
    if not parts:
        return None
    out = d / "audio.m4a"
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        return out
    lst = d / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(out)], check=True, timeout=900, cwd=d)
        return out
    except Exception as e:
        log.warning("concat failed: %s", e)
        return None
    finally:
        lst.unlink(missing_ok=True)


class Meeting:
    """One meeting. on_title(title) is called (from the event loop) when a title is ready."""

    def __init__(self, resume_id: str | None = None, on_title=None, oneshot=None):
        self.on_title = on_title
        self.oneshot = oneshot                 # async (prompt, model) -> str; None = no titles / partial summaries
        if resume_id and (DIR / resume_id / "meta.json").exists():
            self.id = resume_id
            self.dir = DIR / resume_id
            self.meta = json.loads((self.dir / "meta.json").read_text())
            log.info("meeting %s resumed at %s", self.id, _fmt(self.meta["seconds"]))
        else:
            now = datetime.now(ZoneInfo(config.TZ))
            self.id = now.strftime("%Y%m%d-%H%M%S")
            self.dir = DIR / self.id
            self.dir.mkdir(parents=True, exist_ok=True)
            self.meta = {"id": self.id, "started": now.isoformat(timespec="seconds"), "title": "", "state": "recording",
                         "seconds": 0.0, "chars": 0, "chunks": [], "chunk_from": 0, "summary": ""}
            log.info("meeting %s started", self.id)
        self.meta["state"] = "recording"
        self.part: wave.Wave_write | None = None
        self.part_path: Path | None = None
        self.part_bytes = 0
        self.part_n = len(list(self.dir.glob("part-*")))
        self.stt = stt_stream.LongSession(self._line, self.meta["seconds"]) if stt_stream.available() else None
        self.transcript = self.dir / "transcript.txt"
        self.detached_at = 0.0
        self.busy = False                     # a title / partial summary call is running
        self._save()
        ACTIVE[self.id] = self
        self.task = asyncio.get_event_loop().create_task(self._background())

    # ------------------------------------------------------------ audio in
    def feed(self, pcm: bytes):
        if self.part is None:
            self.part_n += 1
            self.part_path = self.dir / f"part-{self.part_n:03d}.wav"
            self.part = wave.open(str(self.part_path), "wb")
            self.part.setnchannels(1)
            self.part.setsampwidth(2)
            self.part.setframerate(16000)
            self.part_bytes = 0
        self.part.writeframes(pcm)
        self.part_bytes += len(pcm)
        self.meta["seconds"] += len(pcm) / 32000
        if self.stt:
            self.stt.feed(pcm)
        if self.part_bytes >= PART_S * 32000:
            self._close_part()

    def _close_part(self):
        if self.part is None:
            return
        self.part.close()
        self.part = None
        p = self.part_path
        asyncio.get_event_loop().run_in_executor(None, _encode, p)
        self._save()

    def _line(self, t: float, text: str):          # called from the STT thread
        with self.transcript.open("a", encoding="utf-8") as f:
            f.write(f"[{_fmt(t)}] {text}\n")
        self.meta["chars"] += len(text) + 1

    @property
    def bytes(self) -> int:
        return int(self.meta["seconds"] * 32000)

    def text(self, start: int = 0) -> str:
        try:
            return self.transcript.read_text(encoding="utf-8")[start:]
        except OSError:
            return ""

    def _save(self):
        (self.dir / "meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------ live title + partial summaries
    async def _background(self):
        try:
            while self.meta["state"] == "recording":
                await asyncio.sleep(15)
                self._save()
                if not self.oneshot or self.busy:
                    continue
                txt = self.text()
                long_enough = len(txt) >= 220 or (self.meta["seconds"] > 90 and len(txt) >= 70)
                if not self.meta["title"] and long_enough:
                    await self._make_title(txt)
                elif self.meta["title"] and not self.meta.get("retitled") and len(txt) >= 4000:
                    self.meta["retitled"] = True             # the topic is clearer after ~15 minutes
                    await self._make_title(txt[:6000])
                if len(txt) - self.meta["chunk_from"] >= CHUNK_CHARS:
                    await self._chunk_summary(txt)
        except asyncio.CancelledError:
            pass

    async def _make_title(self, txt: str):
        self.busy = True
        try:
            t = await self.oneshot("זה תחילת תמלול אוטומטי (עם טעויות) של פגישה. כתוב כותרת קצרה של 2 עד 6 מילים בעברית "
                                   "שמתארת על מה הפגישה. רק הכותרת, בלי מרכאות ובלי נקודה.\n\n" + txt[:6000], "haiku")
            t = t.strip().strip('"״׳\'').splitlines()[0][:80] if t.strip() else ""
            if t:
                self.meta["title"] = t
                self._save()
                log.info("meeting %s title: %s", self.id, t)
                if self.on_title:
                    await self.on_title(self)
        finally:
            self.busy = False

    async def _chunk_summary(self, txt: str):
        self.busy = True
        try:
            start = self.meta["chunk_from"]
            part = txt[start:start + CHUNK_CHARS + 2000]
            s = await self.oneshot("זה קטע מתמלול אוטומטי (עם טעויות) של פגישה ארוכה. סכם אותו בנקודות קצרות בעברית: "
                                   "נושאים, החלטות, משימות (מי ומה) ומספרים חשובים. בלי הקדמה.\n\n" + part, "haiku")
            if s:
                self.meta["chunks"].append({"from": start, "to": start + len(part), "summary": s})
                self.meta["chunk_from"] = start + len(part)
                self._save()
        finally:
            self.busy = False

    # ------------------------------------------------------------ end
    def detach(self):
        """The board disconnected mid-meeting: keep everything, wait for it to resume."""
        self.detached_at = time.time()
        self._save()

    async def finish(self) -> tuple[str, Path]:
        """Stops recording; returns (transcript, summary.md path). The final summary is added by the caller."""
        self.meta["state"] = "processing"
        self.task.cancel()
        self._close_part()
        if self.stt:
            await self.stt.finish()
        # wait for the part encoders, then join the parts into one file to listen to
        for _ in range(600):
            if not list(self.dir.glob("part-*.wav")):
                break
            await asyncio.sleep(0.5)
        await asyncio.to_thread(_concat, self.dir)
        text = self.text()
        md = self.dir / "summary.md"
        md.write_text(f"# {self.meta['title'] or 'פגישה'}\n\n{self.meta['started'][:16].replace('T', ' ')} · "
                      f"{self.meta['seconds'] / 60:.0f} דקות\n", encoding="utf-8")
        self.meta["state"] = "done"
        self._save()
        ACTIVE.pop(self.id, None)
        log.info("meeting %s: %.1f min, %d chars", self.id, self.meta["seconds"] / 60, len(text))
        return text, md

    def summary_source(self) -> str:
        """What to summarize: the whole transcript when it is short, else the partial summaries plus the rest."""
        text = self.text()
        if len(text) <= 14000 or not self.meta["chunks"]:
            return text[:14000] if len(text) <= 14000 else text[:7000] + "\n…\n" + text[-7000:]
        parts = [f"סיכום חלק {i + 1}:\n{c['summary']}" for i, c in enumerate(self.meta["chunks"])]
        rest = text[self.meta["chunk_from"]:]
        if rest.strip():
            parts.append("המשך התמלול:\n" + rest[:8000])
        return "\n\n".join(parts)

    def set_summary(self, summary: str):
        self.meta["summary"] = summary
        self._save()
        md = self.dir / "summary.md"
        with md.open("a", encoding="utf-8") as f:
            f.write(f"\n## סיכום\n\n{summary}\n")

    def cancel(self):
        self.task.cancel()
        try:
            if self.part:
                self.part.close()
        except Exception:
            pass
        if self.stt:
            self.stt.cancel()
        ACTIVE.pop(self.id, None)


def recover():
    """After a server restart: meetings left 'recording' are closed as they are (audio parts encoded, joined)."""
    for meta in DIR.glob("*/meta.json"):
        try:
            m = json.loads(meta.read_text())
        except ValueError:
            continue
        if m.get("state") in ("recording", "processing"):
            d = meta.parent
            for w in d.glob("part-*.wav"):
                _encode(w)
            _concat(d)
            m["state"] = "interrupted"
            meta.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
            log.info("meeting %s recovered after restart", m.get("id"))


# ---------------------------------------------------------------- listing for the admin page / app
def listing() -> list[dict]:
    out = []
    for meta in DIR.glob("*/meta.json"):
        try:
            m = json.loads(meta.read_text())
        except ValueError:
            continue
        d = meta.parent
        out.append({"id": m["id"], "title": m.get("title") or "פגישה", "started": m.get("started", ""),
                    "minutes": round(m.get("seconds", 0) / 60, 1), "state": m.get("state", ""),
                    "has_audio": (d / "audio.m4a").exists() or any(d.glob("part-*.m4a")),
                    "has_summary": bool(m.get("summary"))})
    for md in DIR.glob("*.md"):                                 # meetings recorded before the folders
        out.append({"id": md.stem, "title": "פגישה", "started": datetime.fromtimestamp(md.stat().st_mtime).isoformat(timespec="seconds"),
                    "minutes": round((DIR / f"{md.stem}.wav").stat().st_size / 32000 / 60, 1) if (DIR / f"{md.stem}.wav").exists() else 0,
                    "state": "done", "has_audio": (DIR / f"{md.stem}.wav").exists(), "has_summary": "## סיכום" in md.read_text(encoding="utf-8")})
    return sorted(out, key=lambda x: x["started"], reverse=True)[:100]


def _safe_dir(mid: str) -> Path | None:
    if not mid.replace("-", "").isdigit():
        return None
    return DIR / mid


def detail(mid: str) -> dict | None:
    d = _safe_dir(mid)
    if d is None:
        return None
    if (d / "meta.json").exists():
        m = json.loads((d / "meta.json").read_text())
        try:
            tr = (d / "transcript.txt").read_text(encoding="utf-8")
        except OSError:
            tr = ""
        return {**m, "transcript": tr, "live": mid in ACTIVE}
    md = DIR / f"{mid}.md"
    if md.exists():
        return {"id": mid, "title": "פגישה", "legacy_md": md.read_text(encoding="utf-8"), "state": "done"}
    return None


def audio_file(mid: str) -> Path | None:
    d = _safe_dir(mid)
    if d is None:
        return None
    for p in (d / "audio.m4a", DIR / f"{mid}.wav"):
        if p.exists():
            return p
    parts = sorted(d.glob("part-*.m4a"))
    return parts[0] if parts else None


def delete(mid: str) -> bool:
    d = _safe_dir(mid)
    if d is None or mid in ACTIVE:
        return False
    if d.is_dir():
        shutil.rmtree(d)
        return True
    found = False
    for ext in ("md", "wav"):
        p = DIR / f"{mid}.{ext}"
        if p.exists():
            p.unlink()
            found = True
    return found
