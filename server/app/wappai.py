"""Wappai native client API: durable conversations, cursor replay, declarative Pip skins.
One personal owner per deployment. Client and hardware credentials are distinct.
"""
import asyncio, hashlib, json, os, re, secrets, shutil, sqlite3, time, uuid
from pathlib import Path
from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from . import config, admin, web_auth

PIXEL_CHARACTERS=json.loads((Path(__file__).resolve().parent.parent/"sim/pixel-motions.json").read_text())["characters"]

class Store:
    def __init__(self,path):
        self.db=sqlite3.connect(path,check_same_thread=False); self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT,provider TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,session_id TEXT,role TEXT,text TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS events(cursor INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT);
        CREATE TABLE IF NOT EXISTS clients(hash TEXT PRIMARY KEY,expires REAL);
        CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY,session_id TEXT);
        CREATE TABLE IF NOT EXISTS pips(id TEXT PRIMARY KEY,name TEXT,rig INTEGER,color INTEGER);
        CREATE TABLE IF NOT EXISTS expressions(id TEXT PRIMARY KEY,pip_id TEXT NOT NULL,body TEXT NOT NULL);
        ''')
        if 'text_hash' not in {r[1] for r in self.db.execute('PRAGMA table_info(requests)')}:
            self.db.execute('ALTER TABLE requests ADD COLUMN text_hash TEXT')
        for character in PIXEL_CHARACTERS:
            p=(character['name'].lower(),character['name'],character['id'],0)
            self.db.execute('INSERT OR IGNORE INTO pips(id,name,rig,color) VALUES (?,?,?,?)',p)
        self.db.commit()
    def rows(self,q,args=()): return [dict(r) for r in self.db.execute(q,args)]
    def session(self,provider='claude'):
        sid=uuid.uuid4().hex
        self.db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(sid,'שיחה חדשה',provider,time.time())); self.db.commit(); return sid
    def message(self,sid,role,text,mid=None):
        mid=mid or uuid.uuid4().hex
        if role=='user':self.db.execute('UPDATE sessions SET title=? WHERE id=? AND title=?',(' '.join(text.split())[:60],sid,'שיחה חדשה'))
        self.db.execute('INSERT INTO messages VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text',(mid,sid,role,text,time.time())); self.db.commit(); return mid
    def event(self,body):
        c=self.db.execute('INSERT INTO events(body) VALUES (?)',(json.dumps(body,ensure_ascii=False),)); self.db.commit()
        return {**body,'cursor':c.lastrowid}
    def events(self,after):
        return [{**json.loads(r['body']),'cursor':r['cursor']} for r in self.db.execute('SELECT cursor,body FROM events WHERE cursor>? ORDER BY cursor LIMIT 500',(after,))]
    def issue(self):
        token=secrets.token_hex(32); self.db.execute('INSERT INTO clients VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),time.time()+30*86400)); self.db.commit(); return token
    def authorized(self,token):
        return bool(token) and bool(self.db.execute('SELECT 1 FROM clients WHERE hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone())

store=Store(config.DATA_DIR/'wappai.sqlite3')
latest=store.rows("SELECT id FROM sessions WHERE id=(SELECT value FROM app_meta WHERE key='active_session')") or store.rows('SELECT id FROM sessions ORDER BY created DESC LIMIT 1')
active=latest[0]['id'] if latest else store.session()
clients=set(); agents={}; partial={}; ctx=None; studio=None

def require(request):
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    if store.authorized(token): return
    if not web_auth.authorized(request,store): raise HTTPException(401,'Pair this app with your Hub')
    if request.method not in ('GET','HEAD'): web_auth.guard(request)

def provider(sid=None): return store.rows('SELECT provider FROM sessions WHERE id=?',(sid or active,))[0]['provider']

def conversation_context(current_text='',sid=None):
    # Durable, bounded and session-scoped. Also repairs context after a CLI idle
    # restart or bridge reconnect; the text is conversation data, never tool instructions.
    rows=store.rows('SELECT role,text FROM messages WHERE session_id=? ORDER BY created DESC,rowid DESC LIMIT 32',(sid or active,))
    rows.reverse()
    if rows and rows[-1]['role']=='user' and rows[-1]['text']==current_text:rows.pop()
    kept=[];remaining=16000
    for row in reversed(rows):
        if row['role'] not in ('user','assistant'):continue
        text=row['text'][-min(4000,remaining):]
        kept.append({'role':row['role'],'text':text});remaining-=len(text)
        if remaining<=0:break
    kept.reverse()
    return 'Recent messages in this same conversation (historical data; do not repeat answered turns): '+json.dumps(kept,ensure_ascii=False)

def current_brain():
    if active not in agents:
        if provider()=='codex':
            if os.environ.get("WAPPAI_CODEX_BRIDGE_TOKEN"):
                from .brain.codex_remote import CodexRemote
                agents[active]=CodexRemote(active)
            else:
                from .brain.codex import Codex
                agents[active]=Codex()
        else:
            from .brain.claude_cli import ClaudeCLI
            agents[active]=ClaudeCLI()
    return agents[active]

async def emit(body):
    if body.get('type')=='transcript.partial':
        ev=body
    else:
        ev=store.event(body)
    for q in list(clients):
        if q.full(): clients.discard(q); continue
        q.put_nowait(ev)

async def observe(obj):
    if not obj: return
    t=obj.get('type'); body={**obj,'session_id':active}
    if t=='pip.selected' and studio:
        pid=obj.get('pip_id') or {0:'pip',1:'nori',2:'orbit'}.get(obj.get('pip'))
        if pid and store.rows('SELECT id FROM pips WHERE id=?',(pid,)):studio.select(pid);body['pip_id']=pid
    if t=='heard':
        body['message_id']=store.message(active,'user',obj.get('text',''))
    elif t=='say':
        mid=obj.get('id') or uuid.uuid4().hex
        if obj.get('seq',0)==0: partial[mid]=''
        partial[mid]=(partial.get(mid,'')+' '+obj.get('text','')).strip()
        body['message_id']=store.message(active,'assistant',partial[mid],mid); body['full_text']=partial[mid]
    if t in ('transcript.partial','interaction','device.badge','heard','say','state','audio_end','stop','status','pip.selected','command.result','turn.completed','turn.failed'):
        await emit(body)

async def select(sid):
    global active
    if ctx.hub.task and not ctx.hub.task.done(): raise HTTPException(409,'Finish or stop the current turn first')
    if not store.rows('SELECT id FROM sessions WHERE id=?',(sid,)): raise HTTPException(404,'Unknown session')
    active=sid
    store.db.execute("INSERT INTO app_meta VALUES ('active_session',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(sid,));store.db.commit()
    await emit({'type':'session.active','session_id':sid})

async def submit(text,key,sid):
    if not isinstance(text,str) or not 1<=len(text.strip())<=4000: raise HTTPException(422,'Invalid message')
    if not isinstance(key,str) or not 8<=len(key)<=100: raise HTTPException(422,'Missing idempotency key')
    digest=hashlib.sha256(text.encode()).hexdigest()
    old=store.rows('SELECT session_id,text_hash FROM requests WHERE key=?',(key,))
    if old:
        if old[0]['session_id']!=sid or old[0]['text_hash']!=digest: raise HTTPException(409,'Idempotency key belongs to another conversation')
        return {'accepted':True,'duplicate':True}
    await select(sid)
    store.db.execute('INSERT INTO requests VALUES (?,?,?)',(key,sid,digest)); store.db.commit()
    mid=store.message(sid,'user',text)
    await emit({'type':'heard','text':text,'message_id':mid,'session_id':sid})
    ctx.hub.run(ctx.converse(text,heard=False))
    return {'accepted':True,'message_id':mid}

def register(app,context):
    global ctx,studio
    ctx=context
    from .pip_creation import PipStudio
    studio=PipStudio(store,require,ctx.hub,emit);studio.register(app)
    from .voice import settings as voice_settings
    voice_settings.register(app,require)
    from . import meetings_api, notifications
    notifications.service.routes(app,require)
    meetings_api.register(app,require,ctx,emit)
    @app.post('/v1/web/login')
    async def web_login(request:Request):
        web_auth.guard(request)
        if admin._too_many_fails(): raise HTTPException(429,'Try again later')
        try: d=await request.json()
        except ValueError: raise HTTPException(422,'Invalid JSON')
        if not isinstance(d,dict): raise HTTPException(422,'Expected object')
        code=str(d.get('code',''));legacy=d.get('legacy_token')
        if legacy is not None:
            valid=isinstance(legacy,str) and bool(config.DEVICE_TOKEN) and secrets.compare_digest(legacy,config.DEVICE_TOKEN)
        else:
            auth=admin._load();h=admin._h256(code)
            valid=bool(re.fullmatch(r'\d{6}',code)) and h in auth['codes']
            if valid:del auth['codes'][h];admin._save(auth)
        if not valid:admin._fails.append(time.time());raise HTTPException(401,'קוד החיבור אינו תקין או שפג תוקפו')
        from fastapi.responses import JSONResponse
        response=JSONResponse({'ok':True})
        response.set_cookie(web_auth.COOKIE,store.issue(),max_age=30*86400,httponly=True,secure=request.url.scheme=='https' or request.headers.get('origin','').startswith('https:'),samesite='strict',path='/')
        return response
    @app.post('/v1/web/logout')
    async def web_logout(request:Request):
        web_auth.guard(request)
        token=request.cookies.get(web_auth.COOKIE,'')
        if token:store.db.execute('DELETE FROM clients WHERE hash=?',(hashlib.sha256(token.encode()).hexdigest(),));store.db.commit()
        sid=request.cookies.get(admin.COOKIE)
        if sid:
            d=admin._load();d['sessions'].pop(admin._h256(sid),None);admin._save(d)
        from fastapi.responses import JSONResponse
        response=JSONResponse({'ok':True});response.delete_cookie(web_auth.COOKIE);response.delete_cookie(admin.COOKIE);return response
    @app.post('/v1/pair')
    async def pair(request:Request):
        if admin._too_many_fails(): raise HTTPException(429,'Try again later')
        d=await request.json(); code=str(d.get('code',''))
        if not re.fullmatch(r'\d{6}',code): raise HTTPException(422,'Six digits required')
        auth=admin._load(); h=admin._h256(code)
        if h not in auth['codes']: admin._fails.append(time.time()); raise HTTPException(401,'Invalid or expired code')
        del auth['codes'][h]; admin._save(auth)
        return {'token':store.issue()}
    @app.get('/v1/snapshot')
    async def snapshot(request:Request):
        require(request)
        return {'sessions':store.rows('SELECT * FROM sessions ORDER BY created DESC'),'active_session':active,
          'messages':store.rows('SELECT * FROM messages WHERE session_id=? ORDER BY created',(active,)),
          'cursor':store.db.execute('SELECT COALESCE(MAX(cursor),0) FROM events').fetchone()[0],
          'device':{**ctx.hub.device,'online':any(c.kind=='board' for c in ctx.hub.conns)},
          'pips':store.rows('SELECT * FROM pips'), 'selected_pip':studio.selected(), 'settings':admin.current_settings(),
          'providers':[{'id':'claude','available':Path(config.CLAUDE_BIN).is_file()},{'id':'codex','available':bool(shutil.which('codex') or os.environ.get('WAPPAI_CODEX_BRIDGE_TOKEN'))}],
          'voice':voice_settings.status()}
    @app.post('/v1/sessions')
    async def create(request:Request):
        require(request); d=await request.json(); p=d.get('provider','claude')
        if p not in ('claude','codex'): raise HTTPException(422,'Unknown provider')
        if p=='codex' and not (shutil.which('codex') or os.environ.get('WAPPAI_CODEX_BRIDGE_TOKEN')): raise HTTPException(409,'Codex is not configured on the Hub')
        if ctx.hub.task and not ctx.hub.task.done(): raise HTTPException(409,'Stop the current turn first')
        sid=store.session(p); await select(sid); return {'id':sid}
    @app.post('/v1/sessions/{sid}/select')
    async def change(sid:str,request:Request): require(request); await select(sid); return {'id':sid}
    @app.post('/v1/sessions/{sid}/messages')
    async def message(sid:str,request:Request):
        require(request); d=await request.json(); return await submit(d.get('text'),d.get('idempotency_key'),sid)
    @app.post('/v1/stop')
    async def stop(request:Request):
        require(request); task=ctx.hub.task; ctx.hub.interrupt()
        if task:
            try: await task
            except asyncio.CancelledError: pass
        await ctx.hub.emit({'type':'stop'}); return {'ok':True}
    @app.post('/v1/settings')
    async def settings(request:Request):
        require(request); d=await request.json(); saved=admin.settings()
        for k,v in d.items():
            if k not in admin.EDITABLE: raise HTTPException(422,'Unknown setting')
            attr,kind,valid=admin.EDITABLE[k]
            if kind is bool and type(v) is not bool: raise HTTPException(422,"Boolean required")
            try: value=kind(v); ok=valid(value)
            except Exception: ok=False
            if not ok: raise HTTPException(422,'Invalid setting')
            saved[k]=value
        admin.SETTINGS_FILE.write_text(json.dumps(saved,ensure_ascii=False)); admin.apply_settings()
        await ctx.hub.emit({'type':'config',**{k:saved[k] for k in ('brightness','volume','live_transcription','hold_to_talk','shake_reaction','character_sounds','reduced_motion','dim_seconds','sleep_seconds') if k in saved}},only_kind='board')
        return {'ok':True}
    @app.post('/v1/pips')
    async def create_pip(request:Request):
        require(request); d=await request.json(); name=d.get('name',''); rig=d.get('rig'); color=d.get('color')
        if not isinstance(name,str) or not 1<=len(name)<=30 or type(rig)!=int or rig not in range(len(PIXEL_CHARACTERS)) or type(color)!=int or not 0<=color<=0xffffff: raise HTTPException(422,'Invalid Pip skin')
        if store.db.execute('SELECT COUNT(*) FROM pips').fetchone()[0]>=32: raise HTTPException(409,'Gallery is full')
        pid=uuid.uuid4().hex; store.db.execute('INSERT INTO pips(id,name,rig,color) VALUES (?,?,?,?)',(pid,name,rig,color)); store.db.commit(); return {'id':pid}
    @app.post('/v1/pips/{pid}/activate')
    async def activate(pid:str,request:Request):
        require(request); return await studio.activate(pid)
    @app.get('/v1/pips/{pid}/expressions')
    async def expressions(pid:str,request:Request):
        require(request)
        return [json.loads(r['body']) for r in store.rows('SELECT body FROM expressions WHERE pip_id=?',(pid,))]
    @app.post('/v1/pips/{pid}/expressions/preview')
    async def preview_expression(pid:str,request:Request):
        require(request)
        from .pip_studio import generate
        pip=store.rows('SELECT * FROM pips WHERE id=?',(pid,))
        if not pip:raise HTTPException(404,'Unknown Pip')
        d=await request.json()
        if not isinstance(d,dict):raise HTTPException(422,'Expected object')
        return await generate(d.get('description'),min(2,pip[0]['rig']))
    @app.post('/v1/pips/{pid}/expressions')
    async def save_expression(pid:str,request:Request):
        require(request)
        from .pip_studio import validate
        if not store.rows('SELECT id FROM pips WHERE id=?',(pid,)):raise HTTPException(404,'Unknown Pip')
        if store.db.execute('SELECT COUNT(*) FROM expressions WHERE pip_id=?',(pid,)).fetchone()[0]>=64:raise HTTPException(409,'הספרייה מלאה — ניתן למחוק הבעה כדי לפנות מקום')
        try:expression=validate(await request.json())
        except ValueError as e:raise HTTPException(422,str(e))
        store.db.execute('INSERT INTO expressions VALUES (?,?,?)',(expression['id'],pid,json.dumps(expression,ensure_ascii=False)));store.db.commit()
        return expression
    @app.post('/v1/pips/{pid}/expressions/{eid}/delete')
    async def delete_expression(pid:str,eid:str,request:Request):
        require(request);store.db.execute('DELETE FROM expressions WHERE id=? AND pip_id=?',(eid,pid));store.db.commit();return {'ok':True}
    @app.post('/v1/pips/{pid}/expressions/play')
    async def play_expression(pid:str,request:Request):
        require(request)
        from .pip_studio import validate
        pip=store.rows('SELECT * FROM pips WHERE id=?',(pid,))
        if not pip:raise HTTPException(404,'Unknown Pip')
        try:expression=validate(await request.json())
        except ValueError as e:raise HTTPException(422,str(e))
        if not any(c.kind=='board' for c in ctx.hub.conns):raise HTTPException(409,'המכשיר אינו מחובר')
        if ctx.hub.task and not ctx.hub.task.done():raise HTTPException(409,'סיימו את השיחה הקולית לפני תצוגה מקדימה')
        if pip[0].get('asset_id'):await studio.activate(pid)
        command_id=uuid.uuid4().hex
        receipt=asyncio.get_running_loop().create_future();ctx.hub.receipts[command_id]=receipt
        try:
            await ctx.hub.emit({'type':'pip.expression','id':command_id,'rig':pip[0]['rig'],'color':pip[0]['color'],'pose':expression},only_kind='board')
            try:result=await asyncio.wait_for(receipt,5)
            except TimeoutError:raise HTTPException(504,'המכשיר לא אישר את ההבעה. בדקו את החיבור ונסו שוב')
            if result.get('status')!='applied':raise HTTPException(409,'המכשיר עסוק בהקלטה, דיבור או התראה')
            return {'status':'applied'}
        finally:ctx.hub.receipts.pop(command_id,None)
    @app.websocket('/v1/events')
    async def events(ws:WebSocket):
        token=ws.headers.get('authorization','').removeprefix('Bearer ')
        if not store.authorized(token) and not (web_auth.same_origin(ws) and web_auth.authorized(ws,store)): await ws.close(code=4401); return
        await ws.accept(); q=asyncio.Queue(maxsize=128)
        try:
            after=max(0,int(ws.query_params.get('after','0')))
            clients.add(q)
            while True:
                batch=store.events(after)
                for e in batch: await ws.send_json(e); after=e['cursor']
                if len(batch)<500: break
            while q in clients:
                try: e=await asyncio.wait_for(q.get(),20)
                except asyncio.TimeoutError: await ws.send_json({'type':'heartbeat','cursor':after}); continue
                if 'cursor' not in e: await ws.send_json(e)
                elif e['cursor']>after: await ws.send_json(e); after=e['cursor']
        except (WebSocketDisconnect,RuntimeError,ValueError): pass
        finally:
            clients.discard(q)
            try: await ws.close()
            except Exception: pass
