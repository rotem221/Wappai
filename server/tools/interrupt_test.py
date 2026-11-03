"""Barge-in test for the brain: interrupt a long answer with a new question; the next answers must not contain
leftovers of the interrupted one. Run on the server:  python -m tools.interrupt_test"""
import asyncio, json, time
import websockets
from tools.ws_test import token

async def main():
    async with websockets.connect(f"ws://127.0.0.1:8770/ws?kind=sim&token={token()}", max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "device_id": "interrupt_test"}))
        says: dict[str, list[str]] = {}
        order: list[str] = []

        async def reader():
            async for m in ws:
                if isinstance(m, bytes):
                    continue
                d = json.loads(m)
                if d.get("type") == "say":
                    if d["id"] not in says:
                        says[d["id"]] = []; order.append(d["id"])
                    says[d["id"]].append(d["text"])
        r = asyncio.create_task(reader())
        for q, wait in [("ספר לי סיפור ארוך ומפורט על חתול שיצא להרפתקה בעיר", 2.5),
                        ("עזוב את הסיפור. מה בירת איטליה?", 9), ("ומה בירת צרפת?", 9)]:
            await ws.send(json.dumps({"type": "text", "text": q}))
            await asyncio.sleep(wait)
        r.cancel()
    texts = [" ".join(says[i]) for i in order]
    for i, t in enumerate(texts):
        print(f"answer {i + 1}: {t[:160]}")
    # the story may be cut before its first sentence is out, so judge the last two answers
    ok = len(texts) >= 2 and "רומא" in texts[-2] and "פריז" in texts[-1] and "חתול" not in texts[-2] + texts[-1]
    print("RESULT:", "PASS" if ok else "FAIL")

if __name__ == "__main__":
    asyncio.run(main())
