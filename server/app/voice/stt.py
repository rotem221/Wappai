"""Hebrew speech-to-text with ivrit.ai's Whisper (faster-whisper / CTranslate2, int8 on CPU)."""
import asyncio
import logging
import time

import numpy as np

from .. import config

log = logging.getLogger("stt")
_model = None
_lock = asyncio.Lock()


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        t = time.time()
        _model = WhisperModel(config.STT_MODEL, device="cpu", compute_type="int8", cpu_threads=config.STT_THREADS)
        log.info("STT model loaded in %.1fs", time.time() - t)
    return _model


def _transcribe(pcm: bytes) -> str:
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    # normalise quiet microphones (the board mic is far from the mouth)
    peak = float(np.max(np.abs(audio))) if audio.size else 0
    if 0.001 < peak < 0.5:
        audio = audio * (0.5 / peak)
    segs, _ = _load().transcribe(audio, language=None if config.STT_LANGUAGE == "auto" else config.STT_LANGUAGE, beam_size=2, vad_filter=True,
                                 vad_parameters={"min_silence_duration_ms": 300},
                                 condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs).strip()


async def warmup():
    await asyncio.to_thread(_load)


async def transcribe(pcm: bytes) -> str:
    if len(pcm) < 16000 * 2 * 0.3:      # < 0.3 s
        return ""
    async with _lock:
        t = time.time()
        text = await asyncio.to_thread(_transcribe, pcm)
        log.info("STT %.1fs audio -> %.2fs: %s", len(pcm) / 32000, time.time() - t, text)
        return text
