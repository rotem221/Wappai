"""Streaming Hebrew STT: ivrit.ai zipformer2-66m (sherpa-onnx). Decodes while the user is still talking,
so the text is ready almost immediately when the button is released."""
import asyncio
import logging
import time
from pathlib import Path

import numpy as np

from .. import config

log = logging.getLogger("stt.stream")
_rec = None


def _recognizer():
    global _rec
    if _rec is None:
        import sherpa_onnx
        d = Path(config.STREAM_MODEL_DIR) / "sherpa-onnx"
        t = time.time()
        _rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(d / "tokens.txt"), encoder=str(d / "encoder.int8.onnx"), decoder=str(d / "decoder.int8.onnx"),
            joiner=str(d / "joiner.int8.onnx"), model_type="zipformer2", num_threads=config.STT_THREADS,
            # endpoints are only consulted by long meeting streams (LongSession); push-to-talk ignores them
            enable_endpoint_detection=True, rule1_min_trailing_silence=2.4, rule2_min_trailing_silence=1.0,
            rule3_min_utterance_length=25)
        log.info("streaming STT loaded in %.1fs", time.time() - t)
    return _rec


def available() -> bool:
    return (Path(config.STREAM_MODEL_DIR) / "sherpa-onnx" / "tokens.txt").exists()


async def warmup():
    await asyncio.to_thread(_recognizer)


class Session:
    """One push-to-talk utterance: feed() as audio arrives (in order, off the event loop), finish() on release."""

    def __init__(self, on_partial=None):
        self.on_partial = on_partial
        self.last_partial = ""
        self.partial_at = 0.0
        self.rec = _recognizer()
        self.stream = self.rec.create_stream()
        self.q: asyncio.Queue = asyncio.Queue()
        self.samples = 0
        self.peak = 0.02          # running peak for automatic gain (far-field board mic)
        self.worker = asyncio.create_task(self._run())

    def _feed(self, pcm: bytes):
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if x.size:
            self.peak = max(self.peak * 0.995, float(np.percentile(np.abs(x), 99.5)))
            gain = min(12.0, 0.35 / self.peak)
            x = np.clip(x * gain, -1.0, 1.0)
        self.stream.accept_waveform(16000, x)
        while self.rec.is_ready(self.stream):
            self.rec.decode_stream(self.stream)
        result = self.rec.get_result(self.stream)
        return (result if isinstance(result, str) else getattr(result, "text", str(result))).strip()

    def _finish(self) -> str:
        self.stream.accept_waveform(16000, np.zeros(int(3.0 * 16000), dtype=np.float32))
        self.stream.input_finished()
        while self.rec.is_ready(self.stream):
            self.rec.decode_stream(self.stream)
        r = self.rec.get_result(self.stream)
        return (r if isinstance(r, str) else getattr(r, "text", str(r))).strip()

    async def _run(self) -> str:
        buf = bytearray()
        while True:
            item = await self.q.get()
            if item is None:
                break
            buf += item
            if len(buf) >= 6400:                 # decode in 0.2 s slices
                text = await asyncio.to_thread(self._feed, bytes(buf))
                buf.clear()
                now = time.monotonic()
                if self.on_partial and text and text != self.last_partial and now-self.partial_at >= 0.4:
                    self.last_partial=text;self.partial_at=now
                    await self.on_partial(text)
        if buf:
            await asyncio.to_thread(self._feed, bytes(buf))
        return await asyncio.to_thread(self._finish)

    def feed(self, pcm: bytes):
        self.samples += len(pcm) // 2
        self.q.put_nowait(pcm)

    async def finish(self) -> str:
        t = time.time()
        self.q.put_nowait(None)
        text = await self.worker
        log.info("stream STT %.1fs audio, final %.2fs: %s", self.samples / 16000, time.time() - t, text)
        return text

    def cancel(self):
        self.worker.cancel()


class LongSession(Session):
    """Hours of audio (meetings): the stream is cut at pauses (endpoint detection) so decoding state stays small, and
    every finished sentence goes to on_line(seconds_from_start, text) right away."""

    def __init__(self, on_line, offset_s: float = 0.0):
        self.on_line = on_line
        self.offset = offset_s
        self.seg_start = 0
        super().__init__()

    def _emit(self, text: str):
        if text:
            self.on_line(self.offset + self.seg_start / 16000, text)

    def _feed(self, pcm: bytes):
        super()._feed(pcm)
        if self.rec.is_endpoint(self.stream):
            r = self.rec.get_result(self.stream)
            self._emit((r if isinstance(r, str) else getattr(r, "text", str(r))).strip())
            self.rec.reset(self.stream)
            self.seg_start = self.samples_fed

    def _finish(self) -> str:
        text = super()._finish()
        self._emit(text)
        return ""

    async def _run(self) -> str:
        self.samples_fed = 0
        buf = bytearray()
        while True:
            item = await self.q.get()
            if item is None:
                break
            buf += item
            if len(buf) >= 6400:
                self.samples_fed += len(buf) // 2
                await asyncio.to_thread(self._feed, bytes(buf))
                buf.clear()
        if buf:
            self.samples_fed += len(buf) // 2
            await asyncio.to_thread(self._feed, bytes(buf))
        return await asyncio.to_thread(self._finish)
