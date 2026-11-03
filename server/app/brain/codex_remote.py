"""Authenticated application bridge across an SSH reverse tunnel bound only to loopback."""
import os,json,httpx
class CodexRemote:
    def __init__(self,sid):self.sid=sid;self.last_ok=False
    async def ask(self,text,context=''):
        self.last_ok=False
        headers={'Authorization':'Bearer '+os.environ['WAPPAI_CODEX_BRIDGE_TOKEN']}
        async with httpx.AsyncClient(timeout=httpx.Timeout(180,connect=5)) as c:
            async with c.stream('POST','http://127.0.0.1:18773/turn',headers=headers,json={'session':self.sid,'text':text,'context':context}) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:continue
                    ev=json.loads(line)
                    if 'error' in ev:raise RuntimeError(ev['error'])
                    if 'text' in ev:yield ev['text']
                    if ev.get('complete'):self.last_ok=True
        if not self.last_ok:raise RuntimeError('Codex bridge ended before completion')
    async def reset(self):pass
