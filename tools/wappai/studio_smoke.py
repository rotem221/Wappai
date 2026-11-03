"""Exercise the actual personal Hub expression generation, persistence and cleanup.
No chat-session mutation; no device playback unless --play is explicitly supplied.
"""
import asyncio,hashlib,json,subprocess,sys,time
import httpx
async def main():
    remote='cd /opt/companion/server && runuser -u companion -- /opt/companion/venv/bin/python -c "from app import admin;print(admin.new_code(pair=True))"'
    code=subprocess.run(['ssh','-o','BatchMode=yes','-o','HostKeyAlias=192.168.1.10','root@192.0.2.10',remote],capture_output=True,text=True,check=True).stdout.strip()
    async with httpx.AsyncClient(base_url='https://hub.example.com',timeout=115) as c:
        r=await c.post('/v1/pair',json={'code':code});r.raise_for_status();token=r.json()['token'];c.headers['Authorization']='Bearer '+token
        start=time.monotonic()
        r=await c.post('/v1/pips/pip/expressions/preview',json={'description':'סקרן ושמח, מביט לצד, מרים יד ימין לשלום, תנועה רגועה וצליל עדין'});r.raise_for_status();pose=r.json()
        print(json.dumps({'generated_in_seconds':round(time.monotonic()-start,2),'pose':pose},ensure_ascii=False),flush=True)
        r=await c.post('/v1/pips/pip/expressions',json=pose);r.raise_for_status();saved=r.json()
        try:
            r=await c.get('/v1/pips/pip/expressions');r.raise_for_status();assert saved in r.json()
            if '--play' in sys.argv:
                r=await c.post('/v1/pips/pip/expressions/play',json=pose)
                if r.status_code!=200:raise RuntimeError('Device preview: '+str(r.status_code)+' '+r.json().get('detail',''))
                assert r.json()['status']=='applied';print('Physical device acknowledged expression application.',flush=True)
        finally:
            r=await c.post('/v1/pips/pip/expressions/'+saved['id']+'/delete',json={});r.raise_for_status()
        print('Generated expression validated, saved, fetched, and deleted successfully.',flush=True)
        # Revoke this test token without logging its value.
        digest=hashlib.sha256(token.encode()).hexdigest()
        # Auth expires automatically; keep cleanup out of shell quoting by stdin Python.
        script="from app import wappai\nwappai.store.db.execute('DELETE FROM clients WHERE hash=?',("+repr(digest)+",))\nwappai.store.db.commit()\n"
        subprocess.run(['ssh','-o','BatchMode=yes','-o','HostKeyAlias=192.168.1.10','root@192.0.2.10','cd /opt/companion/server && runuser -u companion -- /opt/companion/venv/bin/python'],input=script,text=True,check=True)
asyncio.run(main())
