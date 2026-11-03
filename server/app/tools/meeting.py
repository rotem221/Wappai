"""Meeting transcription with bounded storage and visible interruption states.

The board streams the mic; nothing big is kept in memory:
  - audio goes to disk in one-minute parts (WAV while recording, then AAC .m4a, ~15 MB per hour);
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
import uuid
import threading
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import config, meeting_storage
from ..voice import stt_stream

log = logging.getLogger("meeting")
DIR = config.DATA_DIR / "meetings"
DIR.mkdir(parents=True, exist_ok=True)
DIR.chmod(0o700)
PART_S = 60                     # seconds of audio per part file
RESUME_S = 600                   # a dropped board may come back within this time and continue the meeting
CHUNK_CHARS = 6000               # partial summary every this many transcript characters
ACTIVE: dict[str, "Meeting"] = {}


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def _encode(wav: Path) -> Path | None:
    """WAV part -> AAC (plays everywhere, including iPhone Safari). Keeps the WAV if ffmpeg fails."""
    out = wav.with_suffix(".encoding.m4a")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "aac", "-b:a", "32k", str(out)],
                       check=True, timeout=600)
        final=wav.with_suffix(".m4a");out.replace(final)
        wav.unlink()
        return final
    except Exception as e:
        log.warning("encode %s failed: %s", wav.name, e)
        out.unlink(missing_ok=True)
        return None


def _concat(d: Path) -> Path | None:
    parts = sorted(p for p in d.glob("part-*.m4a") if ".encoding." not in p.name)
    if parts or list(d.glob("part-*.wav")):
        (d/'audio.m4a').unlink(missing_ok=True)
        receipt=d/'audio.cloud.json'
        if receipt.exists():receipt.replace(d/'audio.stale.cloud.json')
    if list(d.glob("part-*.wav")): return None  # never publish a silently incomplete concatenation
    if not parts:
        return None
    out = d / "audio.joining.m4a"
    if len(parts) == 1:
        shutil.copyfile(parts[0], out)
        out.replace(d/"audio.m4a");return d/"audio.m4a"
    lst = d / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(out)], check=True, timeout=900, cwd=d)
        out.replace(d/"audio.m4a");return d/"audio.m4a"
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
        if resume_id and _safe_dir(resume_id) and (DIR / resume_id / "meta.json").exists():
            self.id = resume_id
            self.dir = DIR / resume_id
            self.meta = json.loads((self.dir / "meta.json").read_text())
            log.info("meeting %s resumed at %s", self.id, _fmt(self.meta["seconds"]))
        else:
            now = datetime.now(ZoneInfo(config.TZ))
            self.id = resume_id if resume_id and _safe_dir(resume_id) else now.strftime("%Y%m%d-%H%M%S") + "-" + str(uuid.uuid4().int)[:10]
            self.dir = DIR / self.id
            self.dir.mkdir(parents=True, exist_ok=True)
            self.meta = {"id": self.id, "started": now.isoformat(timespec="seconds"), "title": "", "state": "recording",
                         "seconds": 0.0, "chars": 0, "chunks": [], "chunk_from": 0, "summary": ""}
            log.info("meeting %s started", self.id)
        self.dir.chmod(0o700)
        self.meta["state"] = "recording"
        self.part: wave.Wave_write | None = None
        self.part_path: Path | None = None
        self.part_bytes = 0
        self.part_n = max([int(p.name.split("-")[1].split(".")[0]) for p in self.dir.glob("part-*")] + [0])
        self.encoders = []
        self.finishing = False
        self.finished = False
        self.lock = threading.RLock()
        self.budget = meeting_storage.capacity()["remaining_seconds"]
        self.last_budget_check = 0.0
        self.stt = stt_stream.LongSession(self._line, self.meta["seconds"]) if stt_stream.available() else None
        self.transcript = self.dir / "transcript.txt"
        self.detached_at = 0.0
        self.busy = False                     # a title / partial summary call is running
        self._save()
        ACTIVE[self.id] = self
        self.task = asyncio.get_event_loop().create_task(self._background())

    # ------------------------------------------------------------ audio in
    def feed_sequenced(self,seq:int,pcm:bytes):
        previous=self.meta.get('last_seq',-1)
        if seq<=previous:return
        if seq!=previous+1:raise ValueError('Out-of-order recording block')
        journal=self.dir/'pending-block.json'
        journal.write_text(json.dumps({'seq':seq,'seconds':self.meta['seconds'],'part_n':self.part_n,'part_bytes':self.part_bytes if self.part else 0,'open':self.part is not None}))
        with journal.open('rb') as f:os.fsync(f.fileno())
        self.feed(pcm)
        # Acknowledge after flushing the audio and the durable cursor, never before.
        if self.part:
            self.part._file.flush();os.fsync(self.part._file.fileno())
        self.meta['last_seq']=seq;self._save()
        journal.unlink(missing_ok=True)

    def feed(self, pcm: bytes):
        if self.finishing or self.meta['state'] != 'recording': raise ValueError('Recording is not active')
        if len(pcm)%2: raise ValueError('PCM must contain complete 16-bit samples')
        if time.monotonic()-self.last_budget_check>5:
            self.budget=meeting_storage.capacity()['remaining_seconds']
            self.last_budget_check=time.monotonic()
        if self.budget<5 or self.meta['seconds']>=18000:
            self.meta['stop_reason']='storage_limit' if self.budget<5 else 'duration_limit'
            self._save()
            raise OSError('Recording capacity reached; existing audio preserved')
        self.budget-=len(pcm)/32000
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
        async def encode_archive():
            output=await asyncio.to_thread(_encode,p)
            if output:
                try: await asyncio.to_thread(meeting_storage.archive,output)
                except Exception:
                    self.meta['cloud_state']='retry_required';self._save()
        self.encoders.append(asyncio.create_task(encode_archive()))
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
        with self.lock:
            temp=self.dir/'meta.tmp'
            temp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=1),encoding='utf-8')
            with temp.open('rb') as f:os.fsync(f.fileno())
            temp.replace(self.dir/'meta.json')

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
        except Exception:
            log.exception("Meeting live title/summary unavailable; audio capture continues")

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
        if self.finishing:
            while not self.finished: await asyncio.sleep(.05)
            return self.text(), self.dir/'summary.md'
        self.finishing=True
        self.meta["state"] = "processing"
        self._save()
        self.task.cancel()
        self._close_part()
        if self.stt:
            await self.stt.finish()
        if self.encoders: await asyncio.gather(*self.encoders,return_exceptions=True)
        else:
            # Retry closed WAVs retained by a failed earlier encoding attempt.
            for wav in self.dir.glob('part-*.wav'):await asyncio.to_thread(_encode,wav)
        output=await asyncio.to_thread(_concat,self.dir)
        if output:
            try:
                await asyncio.to_thread(meeting_storage.archive,output)
                if meeting_storage.capacity()['cloud_configured']:self.meta['cloud_state']='archived'
            except Exception:self.meta['cloud_state']='retry_required'
        text = self.text()
        if not text.strip() and self.meta['seconds']>=.3:
            from ..voice import stt
            # Bounded one-minute parts: no hours-long PCM allocation.
            parts=sorted(p for p in self.dir.glob('part-*.m4a') if '.encoding.' not in p.name)+sorted(self.dir.glob('part-*.wav'))
            offset=0.0
            for part in sorted(parts):
                def decode():
                    return subprocess.run(['ffmpeg','-v','error','-i',str(part),'-f','s16le','-ar','16000','-ac','1','pipe:1'],capture_output=True,check=True,timeout=90).stdout
                pcm=await asyncio.to_thread(decode)
                line=await stt.transcribe(pcm)
                if line:self._line(offset,line)
                offset+=len(pcm)/32000
            text=self.text()
        md = self.dir / "summary.md"
        md.write_text(f"# {self.meta['title'] or 'פגישה'}\n\n{self.meta['started'][:16].replace('T', ' ')} · "
                      f"{self.meta['seconds'] / 60:.0f} דקות\n", encoding="utf-8")
        if text.strip():await asyncio.to_thread(meeting_storage.evict,self.dir)
        self.meta["state"] = "transcribed" if text.strip() else "audio_only"
        self.finished=True
        self._save()
        # Keep the deletion guard until the final summarizer releases the meeting.
        log.info("meeting %s: %.1f min, %d chars", self.id, self.meta["seconds"] / 60, len(text))
        return text, md

    async def prepare_summary_source(self, oneshot) -> str:
        """Cover the complete transcript even when live partial summarization was unavailable."""
        text=self.text()
        if len(text)<=14000:return text
        self.oneshot=oneshot
        while len(text)-self.meta['chunk_from']>6000:
            before=self.meta['chunk_from']
            await self._chunk_summary(text)
            if self.meta['chunk_from']<=before:
                raise RuntimeError('Partial summary failed; full transcript preserved for retry')
        return self.summary_source()

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
        self.meta["state"] = "done"
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
            journal=d/'pending-block.json'
            if journal.exists():
                pending=json.loads(journal.read_text())
                if m.get('last_seq',-1)<pending['seq']:
                    m['seconds']=pending['seconds']
                    # Remove only unacknowledged bytes; the device resends this block.
                    number=pending['part_n'] if pending['open'] else pending['part_n']+1
                    part=d/f'part-{number:03d}.wav'
                    if part.exists():
                        size=pending['part_bytes']
                        with part.open('r+b') as stream:
                            stream.truncate(44+size);stream.seek(4);stream.write((36+size).to_bytes(4,'little'));stream.seek(40);stream.write(size.to_bytes(4,'little'))
                journal.unlink(missing_ok=True)
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
                    "has_audio": (d / "audio.m4a").exists() or (d / "audio.cloud.json").exists() or any(d.glob("part-*.m4a")) or any(d.glob("part-*.wav")),
                    "seconds":m.get("seconds",0), "cloud_state":m.get("cloud_state","local"), "stop_reason":m.get("stop_reason",""),
                    "has_summary": bool(m.get("summary"))})
    for md in DIR.glob("*.md"):                                 # meetings recorded before the folders
        out.append({"id": md.stem, "title": "פגישה", "started": datetime.fromtimestamp(md.stat().st_mtime).isoformat(timespec="seconds"),
                    "minutes": round((DIR / f"{md.stem}.wav").stat().st_size / 32000 / 60, 1) if (DIR / f"{md.stem}.wav").exists() else 0,
                    "state": "done", "has_audio": (DIR / f"{md.stem}.wav").exists(), "has_summary": "## סיכום" in md.read_text(encoding="utf-8")})
    return sorted(out, key=lambda x: x["started"], reverse=True)[:100]


def _safe_dir(mid: str) -> Path | None:
    if not isinstance(mid,str) or len(mid)>64 or not mid.replace("-", "").isdigit():
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
        return {**m, "transcript": tr, "live": mid in ACTIVE,"has_audio":audio_file(mid) is not None or (d/"audio.cloud.json").is_file(),"audio_parts":[p.name for p in audio_parts(mid)]}
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
    parts = audio_parts(mid)
    return parts[0] if len(parts)==1 else None

def audio_parts(mid: str) -> list[Path]:
    d=_safe_dir(mid)
    if d is None or (d/"audio.m4a").exists() or (d/"audio.cloud.json").exists():return []
    return sorted(p for p in d.glob("part-*") if p.suffix in (".wav",".m4a") and ".encoding." not in p.name)


def delete(mid: str) -> bool:
    d = _safe_dir(mid)
    if d is None or mid in ACTIVE:
        return False
    if d.is_dir():
        meeting_storage.delete_archive(d)
        shutil.rmtree(d)
        return True
    found = False
    for ext in ("md", "wav"):
        p = DIR / f"{mid}.{ext}"
        if p.exists():
            p.unlink()
            found = True
    return found
