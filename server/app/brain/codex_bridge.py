"""Local authenticated application bridge. No raw Codex RPC is exposed."""
import asyncio,json,os,secrets
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import StreamingResponse
from .codex import Codex
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
agents={}; gate=asyncio.Lock()
secret=Path(os.environ['WAPPAI_BRIDGE_TOKEN_FILE']).read_text().strip()
@app.post('/turn')
async def turn(request:Request):
    if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401)
    if gate.locked():raise HTTPException(409,'A turn is active')
    d=await request.json();sid=d.get('session','');text=d.get('text','');context=d.get('context','')
    if not isinstance(sid,str) or len(sid)>64 or not isinstance(text,str) or not 1<=len(text)<=4000 or not isinstance(context,str) or len(context)>16000:raise HTTPException(422)
    async def generate():
        async with gate:
            if sid not in agents:
                if len(agents)>=8:
                    old=next(iter(agents));await agents.pop(old).reset()
                agents[sid]=Codex()
            try:
                async for t in agents[sid].ask(text,context):yield json.dumps({'text':t},ensure_ascii=False)+'\n'
                yield '{"complete":true}\n'
            except asyncio.CancelledError:await agents[sid].reset();raise
            except Exception:yield '{"error":"Codex unavailable or turn failed"}\n'
    return StreamingResponse(generate(),media_type='application/x-ndjson')

image_gate=asyncio.Lock()
def image_auth(request):
    if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):raise HTTPException(401)
@app.get('/pip-image/capability')
async def image_capability(request:Request):
    image_auth(request)
    from .pip_images import PipImageProvider
    return {'available':await PipImageProvider().available()}
@app.post('/pip-image')
async def pip_image(request:Request):
    image_auth(request)
    from .pip_images import PipImageProvider
    import base64
    from fastapi.responses import Response
    if int(request.headers.get('content-length','0'))>9_000_000:raise HTTPException(413)
    if image_gate.locked():raise HTTPException(409,'An image job is already running')
    d=await request.json();prompt=d.get('prompt');reference=d.get('reference')
    if not isinstance(prompt,str) or not 1<=len(prompt)<=12000:raise HTTPException(422)
    try:photo=base64.b64decode(reference,validate=True) if reference else None
    except (ValueError,TypeError):raise HTTPException(422)
    if photo and (len(photo)>6_000_000 or not photo.startswith(b'\x89PNG\r\n\x1a\n')):raise HTTPException(422)
    async with image_gate:
        worker=asyncio.create_task(PipImageProvider().generate(prompt,photo))
        try:
            while not worker.done():
                await asyncio.wait({worker},timeout=1)
                if await request.is_disconnected():worker.cancel();raise HTTPException(499,'Image request disconnected')
            return Response(await worker,media_type='image/png')
        except (RuntimeError,TimeoutError) as error:raise HTTPException(502,str(error))
        finally:
            if not worker.done():worker.cancel()
            await asyncio.gather(worker,return_exceptions=True)
