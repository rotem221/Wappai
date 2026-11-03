"""Run on the personal Hub; a six-second device timer must be acknowledged.
Does not call external services/tools other than the configured language model.
"""
import asyncio,json
import websockets
from app import config

async def main():
    async with websockets.connect('ws://127.0.0.1:8770/ws?kind=sim',additional_headers={'Authorization':'Bearer '+config.DEVICE_TOKEN}) as ws:
        await ws.send(json.dumps({'type':'hello','device_id':'wappai-timer-qa'}))
        await ws.send(json.dumps({'type':'text','text':'בדיקת המכשיר: הפעל טיימר לשש שניות בשם בדיקה. השתמש בתגית הטיימר בלבד, ללא כלים חיצוניים.'}))
        async with asyncio.timeout(60):
            async for raw in ws:
                if isinstance(raw,bytes):continue
                event=json.loads(raw)
                if event.get('type')=='ping':await ws.send(json.dumps({'type':'pong'}))
                if event.get('type')=='command.result':
                    assert event.get('status')=='applied',event
                    print('Physical device acknowledged timer application.',flush=True)
                    return
                if event.get('type')=='turn.failed':raise RuntimeError('Timer request failed')
        raise RuntimeError('No device acknowledgement')

asyncio.run(main())
