"""Owner-authenticated meeting library and explicit remote-recording controls."""
import asyncio
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from . import meeting_storage
from .tools import meeting


def register(app, require, ctx, emit):
    @app.get('/v1/meetings')
    async def listing(request:Request):
        require(request)
        return {'items':meeting.listing(),'capacity':await asyncio.to_thread(meeting_storage.capacity),'device_storage':ctx.hub.device.get('storage',{'sd_supported':False,'sd_present':False,'status':'not_reported'}),'recording':any(m.meta['state']=='recording' for m in meeting.ACTIVE.values())}

    @app.post('/v1/meetings/start')
    async def start(request:Request):
        require(request); d=await request.json()
        if d.get('consent') is not True:raise HTTPException(422,'יש לאשר שהמשתתפים מודעים להקלטה ולתמלול')
        if meeting.ACTIVE:raise HTTPException(409,'פגישה קודמת עדיין מוקלטת או מעובדת')
        if not any(c.kind=='board' for c in ctx.hub.conns):raise HTTPException(409,'המכשיר אינו מחובר')
        if (await asyncio.to_thread(meeting_storage.capacity))['remaining_seconds']<60:raise HTTPException(507,'אין די מקום להקלטה. פנו מקום או הגדירו ארכיון ענן.')
        await ctx.hub.emit({'type':'record','mode':'meeting'},only_kind='board')
        for _ in range(60):
            if meeting.ACTIVE:return {'recording':True}
            await asyncio.sleep(.1)
        raise HTTPException(409,'המכשיר לא אישר הקלטה. ודאו שהוא פתוח ואינו עסוק בשליחת הקלטה קודמת.')

    @app.post('/v1/meetings/stop')
    async def stop(request:Request):
        require(request)
        if not any(c.kind=='board' for c in ctx.hub.conns):raise HTTPException(409,'המכשיר לא מחובר; יש לסיים בכפתור המכשיר')
        await ctx.hub.emit({'type':'record_stop'},only_kind='board')
        return {'requested':True}

    @app.get('/v1/meetings/{mid}')
    async def detail(mid:str,request:Request):
        require(request);item=meeting.detail(mid)
        if not item:raise HTTPException(404)
        return item

    @app.post('/v1/meetings/{mid}/retry')
    async def retry(mid:str,request:Request):
        require(request)
        if not meeting.detail(mid):raise HTTPException(404)
        if mid in meeting.ACTIVE:raise HTTPException(409,'הפגישה כבר פעילה')
        if not hasattr(ctx,'finish_meeting'):raise HTTPException(503,'העיבוד אינו זמין')
        mt=meeting.Meeting(mid);ctx.finish_meeting(mt)
        return {'accepted':True}

    @app.get('/v1/meetings/{mid}/audio')
    async def audio(mid:str,request:Request,part:str|None=None):
        require(request);directory=meeting._safe_dir(mid)
        if not directory:raise HTTPException(404)
        if part is not None:
            p=next((p for p in meeting.audio_parts(mid) if p.name==part),None)
            if not p:raise HTTPException(404)
        else:p=meeting.audio_file(mid)
        if p:return FileResponse(p,media_type='audio/mp4' if p.suffix=='.m4a' else 'audio/wav',headers={'Cache-Control':'private, no-store'})
        url=await asyncio.to_thread(meeting_storage.remote_audio,directory)
        if url:return RedirectResponse(url,headers={'Cache-Control':'private, no-store'})
        raise HTTPException(404,'ההקלטה אינה זמינה')

    @app.post('/v1/meetings/{mid}/delete')
    async def delete(mid:str,request:Request):
        require(request)
        if mid in meeting.ACTIVE or (meeting.detail(mid) or {}).get('state')=='processing':raise HTTPException(409,'אי אפשר למחוק פגישה פעילה')
        try:deleted=await asyncio.to_thread(meeting.delete,mid)
        except Exception:raise HTTPException(503,'מחיקת הארכיון נכשלה. החומר המקומי נשמר; נסו שוב.')
        if not deleted:raise HTTPException(404)
        await emit({'type':'meeting.deleted','id':mid})
        return {'ok':True}
