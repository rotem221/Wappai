"""Run on the personal Hub: audio -> STT -> agent -> TTS -> streamed PCM.
Uses its existing device credential in memory; does not print or persist audio/credentials.
"""
import asyncio,json,time
import websockets
from app import config,admin
from app.voice import tts
async def main():
    admin.apply_settings()
    pcm=await tts.synth('שלום, אמור בבקשה רק שהחיבור עובד. אל תפעיל כלים.')
    async with websockets.connect('ws://127.0.0.1:8770/ws?kind=qa',additional_headers={'Authorization':'Bearer '+config.DEVICE_TOKEN}) as ws:
        await ws.send(json.dumps({'type':'hello','device_id':'wappai-voice-qa'}))
        await ws.send(json.dumps({'type':'ptt_start'}))
        for offset in range(0,len(pcm),2048):
            await ws.send(pcm[offset:offset+2048]);await asyncio.sleep(.025)
        started=time.monotonic();await ws.send(json.dumps({'type':'ptt_end'}))
        first=None;audio=0;heard='';said=[]
        async with asyncio.timeout(60):
            async for message in ws:
                if isinstance(message,bytes):
                    audio+=len(message)
                    if first is None:first=round(time.monotonic()-started,2)
                    continue
                event=json.loads(message);kind=event.get('type')
                if kind=='ping':await ws.send(json.dumps({'type':'pong'}))
                if kind=='heard':heard=event['text']
                if kind=='say':said.append(event['text'])
                if kind=='turn.failed':raise RuntimeError('Voice turn failed')
                if kind=='turn.completed':break
        assert heard and said and audio>0,(heard,said,audio)
        print(json.dumps({'heard':heard,'said':said,'first_audio_seconds':first,'pcm_bytes':audio},ensure_ascii=False))
asyncio.run(main())
