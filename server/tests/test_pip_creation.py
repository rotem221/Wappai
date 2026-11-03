import asyncio,base64,hashlib,json,types,uuid,os,tempfile
os.environ["DATA_DIR"]=tempfile.mkdtemp(prefix="wappai-studio-tests-")
os.environ["DEVICE_TOKEN"]="test-device-token-never-production"
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from app import pip_assets,config,wappai
from app.pip_creation import PipStudio

@pytest.fixture
def studio(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    monkeypatch.setattr(config,'DEVICE_TOKEN','device-test')
    store=wappai.Store(tmp_path/'library.db')
    hub=types.SimpleNamespace(task=None,conns=set(),device={},receipts={})
    async def emit(*a,**k):pass
    hub.emit=emit
    def auth(request):
        if request.headers.get('authorization')!='Bearer client-test':raise HTTPException(401)
    studio=PipStudio(store,auth,hub,emit);app=FastAPI();studio.register(app)
    with TestClient(app) as client:yield studio,client,{'Authorization':'Bearer client-test'}

def sheet():
    image=Image.new('RGBA',(384,576),(255,0,255,255));d=ImageDraw.Draw(image)
    for i in range(24):
        x=i%4*96;y=i//4*96
        d.rectangle((x+22,y+16,x+72,y+84),fill=(110,90+i*5,210,255))
        d.rectangle((x+27+i%8,y+30,x+31+i%8,y+35+i//8),fill=(255,255,255,255))
        d.rectangle((x+40,y+60,x+42+i,y+63),fill=(20,20,20,255))
    return pip_assets.png(image)

def test_compiler_transparency_and_content_bounds(tmp_path):
    im=Image.new('RGBA',(64,64),(255,0,255,255));im.putpixel((30,30),(165,45,210,255))
    keyed=pip_assets.cutout(im);assert keyed.getpixel((30,30))[3]==255;assert keyed.getpixel((0,0))[3]==0
    m=pip_assets.compile_pack(sheet(),'a'*32,'b'*32,'Test',tmp_path)
    assert 756<m['bytes']<=160000 and m['frames']==24 and len(m['motions'])==43
    assert hashlib.sha256((tmp_path/'character.bin').read_bytes()).hexdigest()==m['sha256']
    with pytest.raises(ValueError):pip_assets.compile_pack(pip_assets.png(Image.new('RGB',(100,100))),'a'*32,'b'*32,'Bad',tmp_path)

def test_builtin_protection_and_auth(studio):
    s,c,h=studio
    for pid in ['pip','nori','orbit']:
        assert c.post(f'/v1/pips/{pid}/edit',headers=h,json={'name':'bad'}).status_code==403
        assert c.post(f'/v1/pips/{pid}/delete',headers=h,json={}).status_code==403
        assert c.post('/v1/pip-jobs',headers=h,json={'name':'bad','description':'test','target':pid}).status_code==403
    assert c.get('/v1/pip-jobs').status_code==401
    assert c.get('/v1/device/pips/'+'a'*32+'.bin',headers=h).status_code==401
    for body in [[],{}, {'name':42,'description':'test'},{'name':'a','description':42}]:
        assert c.post('/v1/pip-jobs',headers=h,json=body).status_code==422

def make_job(s,status='preview_ready'):
    jid=uuid.uuid4().hex;pid=uuid.uuid4().hex;directory=s.root/jid;directory.mkdir()
    im=pip_assets.png(Image.new('RGBA',(96,96),(10,30,60,255)));(directory/'preview.png').write_bytes(im)
    j=dict(id=jid,pip_id=pid,name='Test',description='test character',status=status,progress=25,created=1,preview_sha=hashlib.sha256(im).hexdigest())
    s.save(j);return j

def test_preview_gate_and_durable_recovery(studio,monkeypatch):
    s,c,h=studio;j=make_job(s);calls=[]
    monkeypatch.setattr(s,'launch',lambda *args:calls.append(args))
    path=f"/v1/pip-jobs/{j['id']}/apply"
    assert c.post(path,headers=h,json={}).status_code==409
    assert c.post(path,headers=h,json={'preview_sha':'stale'}).status_code==409
    assert c.post(path,headers=h,json={'preview_sha':j['preview_sha']}).status_code==200
    assert calls==[(j['id'],'build')]
    assert c.post(path,headers=h,json={'preview_sha':j['preview_sha']}).status_code==409
    approved=make_job(s);completed=make_job(s,'ready')
    recovered=PipStudio(s.store,s.auth,s.hub,s.emit)
    assert recovered.get(approved['id'])['status']=='preview_ready'
    assert recovered.get(completed['id'])['status']=='ready'
    assert recovered.get(j['id'])['status']=='failed'
    assert recovered.get(j['id'])['preview_sha']==j['preview_sha']
    # Opening a migrated database must preserve the three protected seeds.
    assert len(wappai.Store(config.DATA_DIR/'library.db').rows('SELECT * FROM pips'))==3

def test_full_build_publish_assets_and_delete(studio):
    s,c,h=studio;j=make_job(s)
    async def image(*args):return sheet()
    s.image=image;asyncio.run(s.run(j['id'],'build'))
    done=s.get(j['id']);assert done['status']=='ready' and done['frames']==24
    interrupted={**done,'status':'applying'};s.save(interrupted)
    recovered=PipStudio(s.store,s.auth,s.hub,s.emit);assert recovered.get(j['id'])['status']=='ready'
    p=s.pip(j['pip_id']);assert p['rig']==3
    aid=p['asset_id']
    assert c.get(f'/v1/pip-assets/{aid}/atlas.png',headers=h).status_code==200
    assert c.get(f'/v1/pip-assets/{aid}/character.bin',headers=h).status_code==404
    device={'Authorization':'Bearer '+config.DEVICE_TOKEN}
    assert c.get(f'/v1/device/pips/{aid}.bin',headers=device).status_code==200
    assert c.get(f'/v1/pip-assets/{aid}/atlas.png',headers=device).status_code==401
    s.select(p['id'])
    assert c.post(f"/v1/pips/{p['id']}/edit",headers=h,json={'name':'New'}).status_code==200
    renamed=s.pip(p['id']);assert renamed['asset_id']!=aid
    pack=(s.root/'assets'/renamed['asset_id']/'character.bin').read_bytes();assert pack[80:144].rstrip(b'\0')==b'New'
    assert c.post(f"/v1/pips/{p['id']}/delete",headers=h,json={}).status_code==200
    assert s.selected()=='pip' and not (s.root/'assets'/aid).exists()
    assert c.get(f'/v1/device/pips/{aid}.bin',headers=device).status_code==404

def test_activation_requires_applied_receipt(studio):
    s,c,h=studio;s.hub.conns={types.SimpleNamespace} # use a hashable board below
    class Board:kind='board'
    s.hub.conns={Board()}
    async def emit(obj,**kw):s.hub.receipts[obj['command_id']].set_result({'status':'busy'})
    s.hub.emit=emit
    with pytest.raises(HTTPException):asyncio.run(s.activate('nori'))
    assert s.selected()=='' and not s.hub.receipts
    async def applied(obj,**kw):s.hub.receipts[obj['command_id']].set_result({'status':'applied'})
    s.hub.emit=applied;asyncio.run(s.activate('nori'));assert s.selected()=='nori'

def test_invalid_generation_never_replaces_existing(studio):
    s,c,h=studio;j=make_job(s)
    async def broken(*args):return b'not an image'
    s.image=broken;asyncio.run(s.run(j['id'],'build'))
    assert s.get(j['id'])['status']=='failed'
    assert len(s.store.rows('SELECT * FROM pips'))==3

def test_creation_accepts_description_or_normalized_reference(studio,monkeypatch):
    s,c,h=studio;launched=[];monkeypatch.setattr(s,'launch',lambda *args:launched.append(args))
    for body in [dict(name='Original',description='A friendly blue bird'),dict(name='Photo',description='Use this reference',reference=base64.b64encode(sheet()).decode())]:
        r=c.post('/v1/pip-jobs',headers=h,json=body);assert r.status_code==200
        j=r.json();assert j['status']=='preview_generating' and not s.store.rows('SELECT id FROM pips WHERE id=?',(j['pip_id'],))
        if 'reference' in body:assert (s.root/j['id']/'reference.png').read_bytes().startswith(b'\x89PNG')
        assert c.post(f"/v1/pip-jobs/{j['id']}/cancel",headers=h,json={}).status_code==200
        assert s.get(j['id'])['status']=='cancelled'
    assert len(launched)==2
    assert c.post('/v1/pip-jobs',headers=h,json=dict(name='Bad',description='test',reference='not-base64')).status_code==422

def test_custom_redesign_preserves_identity_and_failed_edits(studio):
    s,c,h=studio;j=make_job(s)
    async def image(*args):return sheet()
    s.image=image;asyncio.run(s.run(j['id'],'build'));old=s.pip(j['pip_id'])
    edit=make_job(s);edit.update(pip_id=old['id'],target=old['id'],previous_asset=old['asset_id'],name='Redesigned');s.save(edit)
    asyncio.run(s.run(edit['id'],'build'));new=s.pip(old['id'])
    assert new['id']==old['id'] and new['asset_id']!=old['asset_id'] and new['name']=='Redesigned'
    assert not (s.root/'assets'/old['asset_id']).exists()
    stale=make_job(s);stale.update(pip_id=old['id'],target=old['id'],previous_asset=old['asset_id']);s.save(stale)
    asyncio.run(s.run(stale['id'],'build'))
    assert s.get(stale['id'])['status']=='failed' and s.pip(old['id'])['asset_id']==new['asset_id']

def test_apply_rejects_non_object_json(studio):
    s,c,h=studio;j=make_job(s)
    for value in [[],None,42,'text']:
        assert c.post(f"/v1/pip-jobs/{j['id']}/apply",headers=h,content=json.dumps(value)).status_code==422

def test_cancelling_pack_compilation_removes_unpublished_assets(studio,monkeypatch):
    import threading
    s,c,h=studio;j=make_job(s);started=threading.Event();release=threading.Event();finished=threading.Event()
    compile_pack=pip_assets.compile_pack
    def slow_compile(*args):
        started.set();release.wait(3)
        try:return compile_pack(*args)
        finally:finished.set()
    monkeypatch.setattr(pip_assets,'compile_pack',slow_compile)
    async def image(*args):return sheet()
    s.image=image
    async def exercise():
        task=asyncio.create_task(s.run(j['id'],'build'));assert await asyncio.to_thread(started.wait,2)
        asyncio.get_running_loop().call_later(.1,release.set);task.cancel();await asyncio.gather(task,return_exceptions=True)
        assert await asyncio.to_thread(finished.wait,3)
    asyncio.run(exercise())
    assert s.get(j['id'])['status']=='cancelled'
    assert not s.store.rows('SELECT id FROM pips WHERE id=?',(j['pip_id'],))
    assert not list((s.root/'assets').glob('*'))

def test_request_size_uses_actual_bytes_not_claimed_header(studio):
    s,c,h=studio
    response=c.post('/v1/pip-jobs',headers={**h,'Content-Length':'0'},content=b' '*9_000_001)
    assert response.status_code==413
    assert c.post('/v1/pip-jobs',headers=h,content=b'{broken').status_code==422

def test_timeout_cleans_receipt_and_does_not_claim_selection(studio):
    s,c,h=studio
    class Board:kind='board'
    s.hub.conns={Board()}
    async def exercise():
        with pytest.raises(HTTPException) as error:await s.command({'type':'pip.activate','rig':1},timeout=.01)
        assert error.value.status_code==504
        assert not s.hub.receipts and s.selected()==''
    asyncio.run(exercise())

def test_queued_generation_cancellation_and_provider_failure(studio):
    s,c,h=studio;j=make_job(s,'preview_generating');second=make_job(s,'preview_generating')
    async def exercise():
        started=asyncio.Event();stopped=asyncio.Event()
        async def image(*args):
            started.set()
            try:await asyncio.Event().wait()
            finally:stopped.set()
        s.image=image;s.launch(j['id'],'preview');await started.wait();s.launch(second['id'],'preview')
        queued=s.tasks[second['id']];queued.cancel();await asyncio.gather(queued,return_exceptions=True)
        running=s.tasks[j['id']];running.cancel();await asyncio.gather(running,return_exceptions=True)
        assert stopped.is_set() and not s.tasks
    asyncio.run(exercise())
    assert s.get(j['id'])['status']=='cancelled'
    assert s.get(second['id'])['status']=='cancelled'
    # A queued task can be cancelled before its coroutine enters the handler.
    async def unavailable(*args):raise RuntimeError('Codex unavailable')
    s.image=unavailable;asyncio.run(s.run(j['id'],'preview'));assert s.get(j['id'])['status']=='failed'
    assert len(s.store.rows('SELECT * FROM pips'))==3


def test_device_activations_are_serialized(studio):
    s,c,h=studio
    class Board:kind='board'
    s.hub.conns={Board()}
    async def exercise():
        commands=[]
        async def emit(obj,**kw):
            assert len(s.hub.receipts)==1
            commands.append(obj['rig']);await asyncio.sleep(.01)
            s.hub.receipts[obj['command_id']].set_result({'status':'applied'})
        s.hub.emit=emit
        await asyncio.gather(s.activate('nori'),s.activate('orbit'))
        assert commands==[1,2] and s.selected()=='orbit' and not s.hub.receipts
    asyncio.run(exercise())


def test_repeated_cancel_does_not_interrupt_compiler_cleanup(studio,monkeypatch):
    import threading,httpx
    s,c,h=studio;j=make_job(s,'building');started=threading.Event();release=threading.Event()
    original=pip_assets.compile_pack
    def slow(*args):
        started.set();release.wait(3);return original(*args)
    monkeypatch.setattr(pip_assets,'compile_pack',slow)
    async def image(*args):return sheet()
    s.image=image
    async def exercise():
        s.launch(j['id'],'build');assert await asyncio.to_thread(started.wait,2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app),base_url='http://test',headers=h) as client:
            one=asyncio.create_task(client.post('/v1/pip-jobs/'+j['id']+'/cancel'))
            await asyncio.sleep(.02)
            two=asyncio.create_task(client.post('/v1/pip-jobs/'+j['id']+'/cancel'))
            await asyncio.sleep(.02);release.set()
            responses=await asyncio.gather(one,two)
            assert all(r.status_code==200 for r in responses)
        assert not s.tasks and s.get(j['id'])['status']=='cancelled'
        assert not list((s.root/'assets').glob('*'))
    asyncio.run(exercise())


def test_chroma_key_removes_dark_matte_fringe_without_erasing_violet():
    im=Image.new('RGBA',(32,32),(255,0,255,255))
    im.putpixel((10,10),(172,6,180,255));im.putpixel((11,10),(92,0,104,255))
    im.putpixel((12,10),(165,45,210,255));im.putpixel((13,10),(45,200,180,255))
    result=pip_assets.cutout(im)
    assert result.getpixel((10,10))[3]==0 and result.getpixel((11,10))[3]==0
    assert result.getpixel((12,10))==im.getpixel((12,10))
    assert result.getpixel((13,10))==im.getpixel((13,10))
    # A genuinely transparent authored image is not chroma-keyed at all.
    im.putpixel((0,0),(0,0,0,0));assert pip_assets.cutout(im).tobytes()==im.tobytes()
