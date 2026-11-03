"""Personal deployment smoke test. Creates labeled QA conversations; no external tool actions."""
import asyncio,json,subprocess,time,uuid
from pathlib import Path
import httpx
SERVER='https://hub.example.com'
async def main():
    cmd=['ssh','-o','HostKeyAlias=192.168.1.10','-o','BatchMode=yes','root@192.0.2.10',
      'cd /opt/companion/server && runuser -u companion -- /opt/companion/venv/bin/python -c "from app import admin;print(admin.new_code(pair=True))"']
    code=subprocess.run(cmd,capture_output=True,text=True,check=True).stdout.strip()
    async with httpx.AsyncClient(base_url=SERVER,timeout=20) as client:
        r=await client.post('/v1/pair',json={'code':code});r.raise_for_status()
        client.headers['Authorization']='Bearer '+r.json()['token']
        for provider in ['claude','codex']:
            r=await client.post('/v1/sessions',json={'provider':provider});r.raise_for_status();sid=r.json()['id']
            t=time.monotonic()
            r=await client.post(f'/v1/sessions/{sid}/messages',json={'text':'בדיקת Wappai. השב במילים חיבור תקין בלבד. אל תפעיל כלים.','idempotency_key':uuid.uuid4().hex});r.raise_for_status()
            for _ in range(90):
                await asyncio.sleep(1)
                r=await client.get('/v1/snapshot');r.raise_for_status();snap=r.json()
                answers=[m['text'] for m in snap['messages'] if m['role']=='assistant']
                if answers:
                    print(json.dumps({'provider':provider,'latency_to_text_seconds':round(time.monotonic()-t,2),'answer':answers[-1]},ensure_ascii=False),flush=True)
                    await client.post('/v1/stop',json={});break
            else:raise RuntimeError(provider+' timed out')
        r=await client.post('/v1/sessions',json={'provider':'claude'});r.raise_for_status()
        print('Both provider routes returned text; fresh conversation selected.',flush=True)
asyncio.run(main())
