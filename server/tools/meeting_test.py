"""End-to-end meeting test without the board: synthesize a short Hebrew 'meeting' with the server's TTS, stream it as a
meeting recording over the WebSocket, then print what the server answers and the transcript file it wrote.
Run on the server from /opt/companion/server with the venv:  python -m tools.meeting_test"""
import asyncio, json, time
import websockets
from app.voice import tts
from app.tools import meeting as meeting_mod
from tools.ws_test import token

LINES = ["שלום לכולם, נתחיל את הפגישה.", "החלטנו להעביר את ההשקה ליום חמישי הבא.",
         "דנה אחראית לבדוק את התקציב עד יום שני.", "תודה רבה, נסיים כאן."]

async def main():
    pcm = b"".join([await tts.synth(l) + b"\0" * 16000 for l in LINES])
    print(f"audio {len(pcm) / 32000:.1f}s")
    async with websockets.connect(f"ws://127.0.0.1:8770/ws?kind=sim&token={token()}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_id": "meeting_test"}))
        await ws.send(json.dumps({"type": "ptt_start", "id": "mic", "mode": "meeting"}))
        for i in range(0, len(pcm), 2048):                # ~4x real time
            await ws.send(pcm[i:i + 2048]); await asyncio.sleep(0.016)
        await ws.send(json.dumps({"type": "ptt_end", "id": "mic"}))
        t0 = time.time()
        while time.time() - t0 < 90:
            try:
                m = await asyncio.wait_for(ws.recv(), 45)
            except asyncio.TimeoutError:
                break
            if isinstance(m, bytes):
                continue
            d = json.loads(m)
            if d["type"] in ("ping",):
                continue
            print(f"{time.time() - t0:5.1f}s", json.dumps(d, ensure_ascii=False)[:200])
            if d["type"] == "audio_end" and d.get("final") or d["type"] == "say" and not d.get("audio", True):
                break
    await asyncio.sleep(2)
    last = meeting_mod.listing()[0]
    print("file:", last)
    print((meeting_mod.DIR / f"{last['id']}.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    asyncio.run(main())
