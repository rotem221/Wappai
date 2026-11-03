"""Hebrew text-to-speech: Microsoft neural voices via edge-tts, decoded to 16 kHz mono PCM for the board.

stream() yields PCM while the MP3 is still arriving (ffmpeg decodes from a pipe), so the device starts
speaking ~0.5 s after a sentence is ready instead of after the whole sentence is synthesized.
"""
import asyncio
import logging
import time
from typing import AsyncIterator

import edge_tts

from .. import config

log = logging.getLogger("tts")


# Emotion -> prosody. The Hebrew neural voices have no speaking styles, so feeling comes from rate and pitch:
# brighter and quicker when happy, slower and lower when sad or sleepy. Values are relative to TTS_RATE.
PROSODY = {
    "happy": (6, 6), "joy": (10, 10), "excited": (14, 12), "love": (0, 6), "starstruck": (10, 10), "proud": (4, 4),
    "success": (8, 8), "singing": (4, 10), "mischievous": (6, 6), "wink": (4, 6),
    "surprised": (8, 14), "shocked": (10, 16), "curious": (2, 6),
    "sad": (-14, -10), "crying": (-16, -12), "low_battery": (-10, -6), "relieved": (-6, -2),
    "sleepy": (-18, -12), "yawn": (-20, -14), "bored": (-10, -8), "sleeping": (-20, -14),
    "angry": (6, -4), "furious": (10, -6), "annoyed": (2, -4), "skeptical": (-4, -2), "determined": (2, -2),
    "scared": (12, 8), "nervous": (10, 4), "confused": (-4, 2), "thinking": (-6, -2), "shy": (-6, 2),
}


def _prosody(emotion: str | None) -> tuple[str, str]:
    base = int(config.TTS_RATE.rstrip("%") or 0)
    dr, dp = PROSODY.get(emotion or "", (0, 0))
    if config.TTS_STYLE == "lively" and (emotion or "speaking") in ("speaking", "idle", "happy", "joy", "excited", "success", "proud", "love"):
        dr += 4; dp = min(16, dp + 5)
    r = max(-50, min(50, base + dr))
    return f"{r:+d}%", f"{dp:+d}Hz"


async def stream(text: str, emotion: str | None = None) -> AsyncIterator[bytes]:
    if config.TTS_PROVIDER == "elevenlabs":
        from . import elevenlabs
        async for chunk in elevenlabs.stream(text, emotion):
            yield chunk
        return
    t0 = time.time()
    ff = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "mp3", "-i", "pipe:0", "-ac", "1", "-ar", "16000",
        "-f", "s16le", "-flush_packets", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

    async def feed():
        try:
            rate, pitch = _prosody(emotion)
            com = edge_tts.Communicate(text, config.TTS_VOICE, rate=rate, pitch=pitch)
            async for ch in com.stream():
                if ch["type"] == "audio":
                    ff.stdin.write(ch["data"])
                    await ff.stdin.drain()
        except Exception as e:
            log.warning("tts failed: %s", e)
        finally:
            try:
                ff.stdin.close()
            except Exception:
                pass

    feeder = asyncio.create_task(feed())
    total, first, odd = 0, None, b""
    try:
        while True:
            chunk = await ff.stdout.read(4096)
            if not chunk:
                break
            chunk = odd + chunk                      # keep 16-bit samples aligned
            odd = chunk[-1:] if len(chunk) % 2 else b""
            if odd:
                chunk = chunk[:-1]
            if not chunk:
                continue
            if first is None:
                first = time.time() - t0
            total += len(chunk)
            yield chunk
    finally:
        feeder.cancel()
        if ff.returncode is None:
            try:
                ff.kill()
            except ProcessLookupError:
                pass
        await ff.wait()
    if not total: raise RuntimeError("Speech service returned no audio")
    log.info("TTS %d chars -> %.1fs audio, first audio after %.2fs", len(text), total / 32000, first or -1)


async def synth(text: str, emotion: str | None = None) -> bytes:
    """Whole sentence as PCM s16le 16 kHz mono."""
    buf = bytearray()
    async for c in stream(text, emotion):
        buf += c
    return bytes(buf)
