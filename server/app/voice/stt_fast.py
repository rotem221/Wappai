"""Multilingual fast gate: use the Hebrew streaming model for Hebrew, tiny Whisper for English.
The large multilingual recognizer is a fallback, not on the normal response path.
"""
import asyncio
import numpy as np
from faster_whisper import WhisperModel
from .. import config
_model=None
_lock=asyncio.Lock()
def _load():
    global _model
    if _model is None:
        _model=WhisperModel('Systran/faster-whisper-tiny',device='cpu',compute_type='int8',cpu_threads=config.STT_THREADS)
    return _model
async def warmup():await asyncio.to_thread(_load)
def _recognize(pcm):
    audio=np.frombuffer(pcm,dtype=np.int16).astype(np.float32)/32768
    peak=float(np.max(np.abs(audio))) if audio.size else 0
    if .001<peak<.5:audio*=.5/peak
    segments,info=_load().transcribe(audio,beam_size=1,vad_filter=True,condition_on_previous_text=False)
    # The Hebrew streaming transcript is already available. Whisper segments
    # are lazy: decoding them here wastes a full second pass that is discarded.
    # Keep full decoding for English, where it replaces the Hebrew recognizer.
    if info.language != 'en':
        return info.language, ''
    return info.language,' '.join(s.text.strip() for s in segments).strip()
async def recognize(pcm):
    async with _lock:return await asyncio.to_thread(_recognize,pcm)
