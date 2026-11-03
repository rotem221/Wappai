"""Talk to the running server like the simulator does and print what comes back, with timings.
   python tools/ws_test.py "מה השעה?"          # full conversation (needs Claude signed in)
   python tools/ws_test.py --say "שלום!"       # TTS path only (/api/say)
Run on the server; reads the token from /etc/companion.env."""
import asyncio, json, sys, time
import httpx, websockets

def token():
    for l in open("/etc/companion.env"):
        if l.startswith("DEVICE_TOKEN="):
            return l.split("=", 1)[1].strip()

async def main(args):
    say = args and args[0] == "--say"
    text = (args[1:] if say else args)[0] if args[1 if say else 0:] else "היי, מה שלומך?"
    tok = token()
    async with websockets.connect(f"ws://127.0.0.1:8770/ws?kind=sim&token={tok}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_id": "ws_test"}))
        t0 = time.time(); audio = 0; first_audio = None
        if say:
            async with httpx.AsyncClient() as c:
                await c.post(f"http://127.0.0.1:8770/api/say?token={tok}", json={"text": text, "emotion": "happy"})
        else:
            await ws.send(json.dumps({"type": "text", "text": text}))
        while time.time() - t0 < 120:
            try:
                m = await asyncio.wait_for(ws.recv(), 60)
            except asyncio.TimeoutError:
                break
            if isinstance(m, bytes):
                if first_audio is None:
                    first_audio = time.time() - t0
                    print(f"{first_audio:5.2f}s  << first audio")
                audio += len(m); continue
            d = json.loads(m)
            if d["type"] == "ping":
                continue
            print(f"{time.time() - t0:5.2f}s", json.dumps(d, ensure_ascii=False))
            if d["type"] == "audio_end" and d.get("final"):
                break
        print(f"audio {audio / 32000:.1f}s, first audio after {first_audio}s, total {time.time() - t0:.1f}s")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
