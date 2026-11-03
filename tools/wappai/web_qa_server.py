"""Isolated browser QA server. No device, external AI, TTS, or home control."""
import os, tempfile, asyncio, uuid, json
from pathlib import Path
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='wappai-web-qa-')
os.environ['DEVICE_TOKEN']='isolated-web-qa-device'
port=int(os.environ.get('QA_PORT','8876'))
from app import main, wappai, admin
main.app.router.on_startup.clear()
async def converse(text,heard=True):
    await main.hub.emit({'type':'state','emotion':'thinking'})
    await asyncio.sleep(.2)
    await main.hub.emit({'type':'say','id':uuid.uuid4().hex,'seq':0,'text':'קיבלתי: '+text,'audio':False})
    await main.hub.emit({'type':'turn.completed'})
wappai.ctx.converse=converse
capture={'bytes':0,'count':0}
main.USE_STREAM=False
async def handle_audio(pcm,sess):
    capture['bytes']=len(pcm);capture['count']+=1
    await main.hub.emit({'type':'heard','text':'הקלטת דפדפן לבדיקה'})
    await converse('הקלטת דפדפן לבדיקה')
main.handle_audio=handle_audio
main.hub.device={'board':'ESP32-S3-Touch-AMOLED-1.75C','battery':{'pct':75},'rssi':-56,'fw_version':'QA isolated'}
admin.SETTINGS_FILE.write_text(json.dumps({'live_transcription':False,'brightness':170,'volume':80}))
sid=wappai.active
wappai.store.db.execute('UPDATE sessions SET title=? WHERE id=?',('היום שלי',sid))
wappai.store.message(sid,'user','בוא נתכנן את היום ביחד')
wappai.store.message(sid,'assistant','בשמחה! מה הכי חשוב לך להספיק היום?')
wappai.store.db.commit()
# Job compiler remains off in this fixture; preview approval still uses the production API.
def launch(jid,stage):
    job=wappai.studio.get(jid)
    if stage=='preview':
        import hashlib
        png=(Path(__file__).resolve().parents[2]/'server/sim/pixel-0-0.png').read_bytes()
        (wappai.studio.root/jid/'preview.png').write_bytes(png)
        job.update(status='preview_ready',progress=25,preview_sha=hashlib.sha256(png).hexdigest())
    else:job.update(status='building',progress=30)
    wappai.studio.save(job)
wappai.studio.launch=launch
Path(f'/tmp/wappai-web-qa-code-{port}').write_text(admin.new_code(pair=True))
Path(f'/tmp/wappai-web-qa-admin-{port}').write_text(admin.new_code())
from fastapi import Request
@main.app.post('/__qa/event')
async def test_event(request:Request):
    wappai.require(request)
    await main.hub.emit(await request.json())
    return {'ok':True}
@main.app.get('/__qa/capture')
async def capture_info(request:Request):
    wappai.require(request)
    return capture
@main.app.post('/__qa/disconnect')
async def disconnect_events(request:Request):
    wappai.require(request)
    for queue in list(wappai.clients):
        wappai.clients.discard(queue)
        queue.put_nowait({'type':'qa.disconnect'})
    return {'ok':True}
if __name__=='__main__':
    import uvicorn
    uvicorn.run(main.app,host='127.0.0.1',port=port,log_level='warning')
