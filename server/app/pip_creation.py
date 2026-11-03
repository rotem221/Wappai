"""Durable preview -> approved full atlas -> validated pack -> device receipt."""
import asyncio,base64,hashlib,json,os,re,secrets,shutil,struct,time,uuid,zlib
from pathlib import Path
import httpx
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from . import config,pip_assets

BUILTINS={'pip','nori','orbit'}
ID=re.compile(r'^[a-f0-9]{32}$')
async def json_object(request,limit=9_000_000):
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>limit:raise HTTPException(413,'הבקשה גדולה מדי')
        body.extend(chunk)
    try:value=json.loads(body)
    except (ValueError,UnicodeError):raise HTTPException(422,'בקשת JSON אינה תקינה')
    if not isinstance(value,dict):raise HTTPException(422,'נדרש אובייקט JSON')
    return value

class PipStudio:
    def __init__(self,store,auth,hub,emit):
        self.store=store;self.auth=auth;self.hub=hub;self.emit=emit
        self.root=config.DATA_DIR/'pip-studio';self.root.mkdir(parents=True,exist_ok=True)
        self.tasks={};self.gate=asyncio.Lock();self.device_gate=asyncio.Lock()
        store.db.executescript('CREATE TABLE IF NOT EXISTS pip_jobs(id TEXT PRIMARY KEY,body TEXT NOT NULL,created REAL);CREATE TABLE IF NOT EXISTS pip_meta(key TEXT PRIMARY KEY,value TEXT);')
        columns={r[1] for r in store.db.execute('PRAGMA table_info(pips)')}
        for key in ['asset_id','description']:
            if key not in columns:store.db.execute(f'ALTER TABLE pips ADD COLUMN {key} TEXT')
        for job in self.jobs():
            if job['status'] in ('preview_generating','building','applying'):
                if job.get('asset_id') and store.rows('SELECT id FROM pips WHERE asset_id=?',(job['asset_id'],)):
                    job.update(status='ready',installed=False,installation_error='השרת הופעל מחדש. אפשר לטעון את הדמות מהגלריה.');self.save(job);continue
                job.update(status='failed',error='היצירה הופסקה כשהשרת הופעל מחדש. אפשר להמשיך מהתצוגה המקדימה או לנסות שוב.');self.save(job)
        store.db.commit()
    def jobs(self,all=False):return [json.loads(r['body']) for r in self.store.rows('SELECT body FROM pip_jobs ORDER BY created DESC'+('' if all else ' LIMIT 64'))]
    def get(self,jid):
        rows=self.store.rows('SELECT body FROM pip_jobs WHERE id=?',(jid,))
        if not rows:raise HTTPException(404,'היצירה לא נמצאה')
        return json.loads(rows[0]['body'])
    def save(self,j):
        j['updated']=time.time();self.store.db.execute('INSERT INTO pip_jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(j['id'],json.dumps(j,ensure_ascii=False),j['created']));self.store.db.commit()
    def selected(self):
        rows=self.store.rows("SELECT value FROM pip_meta WHERE key='selected'");return rows[0]['value'] if rows else ''
    def select(self,pid):
        self.store.db.execute("INSERT INTO pip_meta VALUES ('selected',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(pid,));self.store.db.commit()
    def pip(self,pid):
        rows=self.store.rows('SELECT * FROM pips WHERE id=?',(pid,))
        if not rows:raise HTTPException(404,'הדמות לא נמצאה')
        return rows[0]
    def writable(self,pid):
        p=self.pip(pid)
        if pid in BUILTINS:raise HTTPException(403,'דמויות ברירת המחדל מוגנות מעריכה וממחיקה')
        return p
    async def image(self,prompt,reference=None):
        token=os.environ.get('WAPPAI_CODEX_BRIDGE_TOKEN')
        if not token:raise RuntimeError('חיבור יצירת התמונות של Codex אינו מוגדר')
        async with httpx.AsyncClient(timeout=httpx.Timeout(440,connect=10)) as client:
            response=await client.post('http://127.0.0.1:18773/pip-image',headers={'Authorization':'Bearer '+token},json={'prompt':prompt,'reference':base64.b64encode(reference).decode() if reference else None})
            if response.status_code!=200:raise RuntimeError('Codex לא השלים את התמונה. בדקו חיבור ומכסת יצירת תמונות ונסו שוב.')
            return response.content
    def launch(self,jid,kind):
        if jid in self.tasks and not self.tasks[jid].done():raise HTTPException(409,'היצירה כבר מתבצעת')
        task=asyncio.create_task(self.run(jid,kind));self.tasks[jid]=task
        def finished(done):
            if self.tasks.get(jid) is not done:return
            self.tasks.pop(jid,None)
            if done.cancelled():
                job=self.get(jid)
                if job['status'] in ('preview_generating','building'):
                    job.update(status='cancelled',error='היצירה בוטלה');self.save(job)
        task.add_done_callback(finished)
    async def run(self,jid,kind):
        job=self.get(jid);directory=self.root/jid
        try:
            async with self.gate:
                if kind=='preview':
                    reference=(directory/'reference.png').read_bytes() if (directory/'reference.png').exists() else None
                    raw=await self.image(pip_assets.preview_prompt(job['description']),reference)
                    (directory/'preview-source.png').write_bytes(raw)
                    result=await asyncio.to_thread(pip_assets.preview,raw);(directory/'preview.png').write_bytes(result)
                    job.update(status='preview_ready',progress=25,preview_sha=hashlib.sha256(result).hexdigest(),error='');self.save(job)
                else:
                    approved=(directory/'preview.png').read_bytes()
                    job.update(progress=35);self.save(job)
                    raw=await self.image(pip_assets.atlas_prompt(),approved);(directory/'atlas-source.png').write_bytes(raw)
                    job.update(progress=75);self.save(job)
                    asset_id=uuid.uuid4().hex;asset_dir=self.root/'assets'/asset_id
                    compiler=asyncio.create_task(asyncio.to_thread(pip_assets.compile_pack,raw,job['pip_id'],asset_id,job['name'],asset_dir))
                    try:manifest=await asyncio.shield(compiler)
                    except asyncio.CancelledError:
                        # Thread work cannot be cancelled. Join it before deleting its output,
                        # otherwise it can recreate an orphan pack after cancellation returns.
                        await asyncio.gather(compiler,return_exceptions=True)
                        shutil.rmtree(asset_dir,ignore_errors=True)
                        raise
                    # Publish only after every pose, byte bound and checksum validates.
                    if job.get('target'):
                        current=self.writable(job['target'])
                        if current.get('asset_id')!=job.get('previous_asset'):raise RuntimeError('הדמות השתנתה מאז פתיחת העריכה. פתחו אותה מחדש.')
                        self.store.db.execute('UPDATE pips SET name=?,rig=3,color=0,asset_id=?,description=? WHERE id=?',(job['name'],asset_id,job['description'],job['pip_id']))
                    else:
                        if self.store.db.execute('SELECT COUNT(*) FROM pips').fetchone()[0]>=32:raise RuntimeError('גלריית הדמויות מלאה')
                        self.store.db.execute('INSERT INTO pips(id,name,rig,color,asset_id,description) VALUES (?,?,3,0,?,?)',(job['pip_id'],job['name'],asset_id,job['description']))
                    job.update(status='ready',progress=100,asset_id=asset_id,frames=24,motions=len(pip_assets.MOTIONS),error='');self.save(job)
                    if job.get('previous_asset'):shutil.rmtree(self.root/'assets'/job['previous_asset'],ignore_errors=True)
                    await self.emit({'type':'pips.updated'})
                    if any(c.kind=='board' for c in self.hub.conns):
                        try:
                            job['status']='applying';self.save(job);await self.activate(job['pip_id']);job['installed']=True
                        except HTTPException as error:job['installed']=False;job['installation_error']=str(error.detail)
                        job['status']='ready';self.save(job)
        except asyncio.CancelledError:
            job.update(status='cancelled',error='היצירה בוטלה');self.save(job);raise
        except Exception as error:
            if 'asset_dir' in locals() and not self.store.rows('SELECT id FROM pips WHERE asset_id=?',(asset_id,)):shutil.rmtree(asset_dir,ignore_errors=True)
            job.update(status='failed',error=str(error) if isinstance(error,(ValueError,RuntimeError)) else 'היצירה לא הושלמה. אפשר לנסות שוב.',failure_stage=kind);self.save(job)
        finally:
            if self.tasks.get(jid) is asyncio.current_task():self.tasks.pop(jid,None)
    async def command(self,payload,timeout=35):
        if not any(c.kind=='board' for c in self.hub.conns):raise HTTPException(409,'המכשיר אינו מחובר. הדמות נשמרה בגלריה.')
        if self.hub.task and not self.hub.task.done():raise HTTPException(409,'סיימו את השיחה הקולית לפני החלפת הדמות')
        command_id=uuid.uuid4().hex;receipt=asyncio.get_running_loop().create_future();self.hub.receipts[command_id]=receipt
        try:
            await self.hub.emit({**payload,'command_id':command_id},only_kind='board')
            try:result=await asyncio.wait_for(receipt,timeout)
            except TimeoutError:raise HTTPException(504,'המכשיר לא אישר את השינוי. בדקו את החיבור ונסו שוב.')
            if result.get('status')!='applied':raise HTTPException(409,'המכשיר לא יישם את השינוי: '+str(result.get('reason',{'storage':'אין אפשרות לשמור באחסון המכשיר','invalid':'חבילת הדמות אינה תקינה','download':'ההורדה לא הושלמה','network':'שגיאת חיבור','busy':'המכשיר עסוק'}.get(result.get('status'),'חבילה לא תקינה')))[:100])
        finally:self.hub.receipts.pop(command_id,None)
    async def activate(self,pid):
        async with self.device_gate:return await self._activate(pid)
    async def _activate(self,pid):
        p=self.pip(pid)
        if p.get('asset_id'):
            manifest=json.loads((self.root/'assets'/p['asset_id']/'manifest.json').read_text())
            await self.command({'type':'pip.install','pip_id':pid,'asset_id':p['asset_id'],'sha256':manifest['sha256'],'bytes':manifest['bytes']},60)
        else:await self.command({'type':'pip.activate','pip_id':pid,'rig':p['rig'],'color':p['color']})
        self.select(pid)
        for job in self.jobs(True):
            if job['pip_id']==pid and job.get('asset_id')==p.get('asset_id'):
                job.update(installed=True,installation_error='');self.save(job)
        await self.emit({'type':'pip.selected','pip':p['rig'],'pip_id':pid});return {'status':'applied'}
    async def restore(self):
        try:
            stale=self.hub.device.get('custom_pip_id')
            if stale and not self.store.rows('SELECT id FROM pips WHERE id=?',(stale,)):
                await self.command({'type':'pip.remove','pip_id':stale})
            pid=self.selected()
            if pid:await self.activate(pid)
        except (HTTPException,OSError,ValueError):pass
    def register(self,app):
        @app.get('/v1/pip-jobs')
        async def jobs(request:Request):self.auth(request);return self.jobs()
        @app.post('/v1/pip-jobs')
        async def create(request:Request):
            self.auth(request)
            d=await json_object(request)
            if not isinstance(d,dict) or not isinstance(d.get('name'),str) or not isinstance(d.get('description'),str) or d.get('target') is not None and not isinstance(d['target'],str):raise HTTPException(422,'שם ותיאור לא תקינים')
            name=d['name'].strip();brief=d['description'].strip();target=d.get('target')
            if not 1<=len(name)<=30 or len(name.encode())>63 or not 3<=len(brief)<=1200:raise HTTPException(422,'יש להזין שם ותיאור של הדמות')
            old=self.writable(target) if target else None
            if len(self.tasks)>=2:raise HTTPException(409,'כבר מתבצעות שתי יצירות; המתינו לסיום')
            reference=None
            if d.get('reference'):
                try:reference=pip_assets.png(pip_assets.read_image(base64.b64decode(d['reference'],validate=True)))
                except Exception:raise HTTPException(422,'התמונה המצורפת אינה תקינה')
            if reference is None and old and old.get('asset_id'):reference=(self.root/'assets'/old['asset_id']/'preview.png').read_bytes()
            jid=uuid.uuid4().hex;directory=self.root/jid;directory.mkdir()
            if reference:(directory/'reference.png').write_bytes(reference)
            job={'id':jid,'pip_id':target or uuid.uuid4().hex,'name':name,'description':brief,'target':target,'previous_asset':old.get('asset_id') if old else None,'status':'preview_generating','progress':5,'created':time.time(),'error':''}
            self.save(job);self.launch(jid,'preview');return job
        @app.get('/v1/pip-jobs/{jid}')
        async def status(jid:str,request:Request):self.auth(request);return self.get(jid)
        @app.get('/v1/pip-jobs/{jid}/preview.png')
        async def job_preview(jid:str,request:Request):
            self.auth(request);self.get(jid);path=self.root/jid/'preview.png'
            if not path.is_file():raise HTTPException(404)
            return FileResponse(path,media_type='image/png')
        @app.post('/v1/pip-jobs/{jid}/apply')
        async def apply(jid:str,request:Request):
            self.auth(request);job=self.get(jid);d=await json_object(request)
            if len(self.tasks)>=2 or jid in self.tasks:raise HTTPException(409,'יש להמתין לסיום היצירה הפעילה')
            if job['status'] not in ('preview_ready','failed'):raise HTTPException(409,'יש להמתין לתצוגה המקדימה')
            if not job.get('preview_sha') or d.get('preview_sha')!=job['preview_sha']:raise HTTPException(409,'יש לאשר את התצוגה המקדימה הנוכחית')
            if job.get('target'):self.writable(job['target'])
            job.update(status='building',progress=30,error='');self.save(job);self.launch(jid,'build');return job
        @app.post('/v1/pip-jobs/{jid}/cancel')
        async def cancel(jid:str,request:Request):
            self.auth(request);job=self.get(jid)
            if job['status'] in ('applying','ready'):raise HTTPException(409,'ממתינים לאישור המכשיר')
            task=self.tasks.get(jid)
            if task:
                # Repeated cancellation must not interrupt the compiler cleanup join.
                if not task.cancelling():task.cancel()
                await asyncio.shield(asyncio.gather(task,return_exceptions=True))
            else:job.update(status='cancelled');self.save(job)
            return {'ok':True}
        @app.get('/v1/pip-assets/{aid}/{file}')
        async def asset(aid:str,file:str,request:Request):
            self.auth(request)
            if not ID.fullmatch(aid) or file not in ('atlas.png','preview.png','manifest.json'):raise HTTPException(404)
            if not self.store.rows('SELECT id FROM pips WHERE asset_id=?',(aid,)):raise HTTPException(404)
            path=self.root/'assets'/aid/file
            if not path.is_file():raise HTTPException(404)
            return FileResponse(path)
        @app.get('/v1/device/pips/{aid}.bin')
        async def binary(aid:str,request:Request):
            if not config.DEVICE_TOKEN or not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+config.DEVICE_TOKEN):raise HTTPException(401)
            if not ID.fullmatch(aid) or not self.store.rows('SELECT id FROM pips WHERE asset_id=?',(aid,)):raise HTTPException(404)
            return FileResponse(self.root/'assets'/aid/'character.bin',media_type='application/octet-stream')
        @app.post('/v1/pips/{pid}/edit')
        async def edit(pid:str,request:Request):
            self.auth(request);p=self.writable(pid);d=await json_object(request)
            if not isinstance(d,dict) or not isinstance(d.get('name'),str):raise HTTPException(422,'שם לא תקין')
            name=d['name'].strip()
            if not 1<=len(name)<=30 or len(name.encode())>63:raise HTTPException(422,'שם לא תקין')
            if any(j['pip_id']==pid and j['id'] in self.tasks for j in self.jobs(True)):raise HTTPException(409,'המתינו לסיום יצירת הדמות')
            aid=p.get('asset_id')
            if aid:
                revised=uuid.uuid4().hex;source=self.root/'assets'/aid;dest=self.root/'assets'/revised
                shutil.copytree(source,dest)
                pack=bytearray((source/'character.bin').read_bytes());pack[48:80]=revised.encode();pack[80:144]=name.encode().ljust(64,b'\0');pack[-4:]=struct.pack('<I',zlib.crc32(pack[:-4]))
                (dest/'character.bin').write_bytes(pack);manifest=json.loads((dest/'manifest.json').read_text());manifest['sha256']=hashlib.sha256(pack).hexdigest();(dest/'manifest.json').write_text(json.dumps(manifest))
                self.store.db.execute('UPDATE pips SET name=?,asset_id=? WHERE id=?',(name,revised,pid))
            else:self.store.db.execute('UPDATE pips SET name=? WHERE id=?',(name,pid))
            self.store.db.commit()
            if aid:shutil.rmtree(self.root/'assets'/aid,ignore_errors=True)
            await self.emit({'type':'pips.updated'})
            if self.selected()==pid:
                try:await self.activate(pid)
                except HTTPException:pass
            return {'ok':True}
        @app.post('/v1/pips/{pid}/delete')
        async def delete(pid:str,request:Request):
            self.auth(request);p=self.writable(pid)
            if any(j['pip_id']==pid and j['id'] in self.tasks for j in self.jobs(True)):raise HTTPException(409,'בטלו קודם את היצירה הפעילה')
            async with self.device_gate:
                if any(c.kind=='board' for c in self.hub.conns):
                    if self.selected()==pid:await self._activate('pip')
                    if p.get('asset_id'):await self.command({'type':'pip.remove','pip_id':pid})
            if self.selected()==pid:self.select('pip')
            for job in self.jobs(True):
                if job['pip_id']==pid:
                    if job['id'] in self.tasks:raise HTTPException(409,'בטלו קודם את היצירה הפעילה')
            self.store.db.execute('DELETE FROM expressions WHERE pip_id=?',(pid,));self.store.db.execute('DELETE FROM pips WHERE id=?',(pid,));self.store.db.commit()
            for job in self.jobs(True):
                if job['pip_id']==pid:
                    self.store.db.execute('DELETE FROM pip_jobs WHERE id=?',(job['id'],));shutil.rmtree(self.root/job['id'],ignore_errors=True)
            self.store.db.commit()
            if p.get('asset_id'):shutil.rmtree(self.root/'assets'/p['asset_id'],ignore_errors=True)
            await self.emit({'type':'pips.updated'});return {'ok':True}
