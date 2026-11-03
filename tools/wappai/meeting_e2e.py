"""Run on the owner's Hub: synthetic Hebrew meeting, durable ACK, duplicate, reconnect, transcript, summary.
No speaker playback and no Home Assistant tools. Retains a labeled QA meeting for inspection.
"""
import asyncio,json,time
import websockets,httpx
from app import config,admin
from app.voice import tts,adpcm
from app.tools import meeting

async def main():
    admin.apply_settings()
    pcm=await tts.synth('זוהי פגישת בדיקה של ואפאי. ההשקה תהיה ביום חמישי. דנה תבדוק את התקציב עד יום שני. יוסי יכין את המצגת. תודה, הפגישה הסתיימה.')
    session=str(int(time.time()))+'-90001'
    headers={'Authorization':'Bearer '+config.DEVICE_TOKEN}
    chunks=[adpcm.encode(pcm[i:i+4096]) for i in range(0,len(pcm),4096)]
    async def connect():
        ws=await websockets.connect('ws://127.0.0.1:8770/ws?kind=qa',additional_headers=headers)
        await ws.send(json.dumps({'type':'ptt_start','mode':'meeting','codec':'adpcm','sequenced':True,'resume':session}))
        while True:
            d=json.loads(await ws.recv())
            if d.get('type')=='meeting':assert d['id']==session;return ws
    async def send(ws,seq):
        await ws.send(b'WAP1'+seq.to_bytes(4,'little')+chunks[seq])
        while True:
            raw=await asyncio.wait_for(ws.recv(),10)
            if isinstance(raw,bytes):continue
            d=json.loads(raw)
            if d.get('type')=='meeting.ack':assert d['seq']==seq;return
    ws=await connect()
    for seq in range(len(chunks)):
        await send(ws,seq)
        if seq==3:await send(ws,seq) # duplicate must not add duration
        if seq==6:
            await ws.close();await asyncio.sleep(.5);ws=await connect();await send(ws,seq)
        await asyncio.sleep(.07)
    await ws.send(json.dumps({'type':'ptt_end'}));await ws.close()
    expected=sum(len(adpcm.decode(c)) for c in chunks)/32000
    print(json.dumps({'meeting_id':session,'expected_seconds':expected,'chunks':len(chunks),'duplicate_and_reconnect':'acknowledged'}),flush=True)
    for _ in range(180):
        item=meeting.detail(session)
        if item and item.get('state') in ('done','audio_only','processing_failed','summary_unavailable'):
            assert abs(item['seconds']-expected)<.001,(item['seconds'],expected)
            assert item['state']=='done',item['state']
            assert len(item.get('transcript',''))>20 and len(item.get('summary',''))>20
            print(json.dumps({'state':item['state'],'seconds':item['seconds'],'transcript_chars':len(item['transcript']),'summary_chars':len(item['summary']),'audio_exists':meeting.audio_file(session) is not None}),flush=True);return
        await asyncio.sleep(1)
    raise TimeoutError('Meeting finalization did not complete')
asyncio.run(main())
