"""Pinned Codex 0.164 app-server protocol over private stdio; never a public raw RPC port."""
import asyncio, json, os, shutil
from pathlib import Path

class Codex:
    def __init__(self):
        self.proc=None; self.thread=None; self.turn=None; self.seq=0
        self.lock=asyncio.Lock(); self.last_ok=False
    async def reset(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try: await asyncio.wait_for(self.proc.wait(),5)
            except asyncio.TimeoutError: self.proc.kill(); await self.proc.wait()
        self.proc=None; self.thread=None; self.turn=None
    async def send(self, msg):
        self.proc.stdin.write((json.dumps(msg,ensure_ascii=False)+'\n').encode()); await self.proc.stdin.drain()
    async def read(self):
        line=await asyncio.wait_for(self.proc.stdout.readline(),120)
        if not line: raise RuntimeError('Codex disconnected')
        ev=json.loads(line)
        if 'method' in ev and 'id' in ev:
            # No implicit grants: sensitive tools remain denied until the approval UI implements them.
            method=ev['method']
            if method.endswith('requestApproval'):
                await self.send({'id':ev['id'],'result':{'decision':'decline'}})
            else:
                await self.send({'id':ev['id'],'error':{'code':-32601,'message':'Unsupported interaction'}})
        return ev
    async def rpc(self, method, params):
        self.seq+=1; rid=self.seq
        await self.send({'id':rid,'method':method,'params':params})
        while True:
            ev=await self.read()
            if ev.get('id')==rid and 'method' not in ev:
                if 'error' in ev: raise RuntimeError(str(ev['error'].get('message','Codex RPC failed')))
                return ev.get('result',{})
    async def ensure(self):
        if self.proc and self.proc.returncode is None: return
        binary=shutil.which(os.environ.get('CODEX_BIN','codex'))
        if not binary: raise RuntimeError('Codex is not configured on this host')
        work=Path(os.environ.get('WAPPAI_AGENT_DIR',str(Path.home()/'.local/share/wappai/agent')))
        work.mkdir(parents=True,exist_ok=True)
        self.proc=await asyncio.create_subprocess_exec(binary,'app-server','--listen','stdio://',cwd=work,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=4*1024*1024)
        await self.rpc('initialize',{'clientInfo':{'name':'wappai','title':'Wappai','version':'1.0.0'},'capabilities':{'experimentalApi':False}})
        await self.send({'method':'initialized'})
        result=await self.rpc('thread/start',{'cwd':str(work),'sandbox':'read-only','approvalPolicy':'untrusted',
            'developerInstructions':'אתה Wappai, עוזר אישי. ענה בעברית בקצרה, הבן גם אנגלית. אל תטען שביצעת פעולה בלי אישור כלי. אל תיגש לקבצים אישיים. רק כלים שהמשתמש אישר.'})
        self.thread=result['thread']['id']
    async def ask(self,text,context=''):
        async with self.lock:
            try:
                await self.ensure()
                r=await self.rpc('turn/start',{'threadId':self.thread,'input':[{'type':'text','text':f'{context}\n{text}','text_elements':[]}]})
                self.turn=r['turn']['id']; chunks=[]
                while True:
                    e=await self.read(); p=e.get('params',{}); m=e.get('method')
                    if p.get('threadId') not in (None,self.thread): continue
                    if m=='item/agentMessage/delta':
                        chunks.append(p.get('delta','')); yield p.get('delta','')
                    elif m=='turn/completed' and p.get('turn',{}).get('id')==self.turn:
                        self.last_ok=p['turn'].get('status')=='completed'
                        if not self.last_ok: raise RuntimeError('Codex turn did not complete')
                        break
            except asyncio.CancelledError:
                if self.proc and self.thread and self.turn:
                    try: await self.send({'id':999999,'method':'turn/interrupt','params':{'threadId':self.thread,'turnId':self.turn}})
                    finally: await self.reset() # no late output can leak into a new turn
                raise
            except Exception:
                self.last_ok=False; await self.reset(); raise
