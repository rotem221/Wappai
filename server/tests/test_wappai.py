import asyncio, os, tempfile, types, uuid
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='wappai-test-')
os.environ['DEVICE_TOKEN']='test-device-token-never-production'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import wappai, admin

class Hub:
    task=None; device={}; conns=set()
    async def emit(self,obj,**kwargs): await wappai.observe(obj)
    def interrupt(self):
        if self.task:self.task.cancel()
    def run(self,coro):self.task=asyncio.create_task(coro)
async def converse(text,heard=True):return None
hub=Hub(); app=FastAPI();wappai.register(app,types.SimpleNamespace(hub=hub,converse=converse))
c=TestClient(app)
def auth():return {'Authorization':'Bearer '+wappai.store.issue()}
def test_auth_required():
    assert c.get('/v1/snapshot').status_code==401
    assert c.get('/v1/snapshot',headers={'Authorization':'Bearer test-device-token-never-production'}).status_code==401
    assert c.get('/v1/snapshot',headers=auth()).status_code==200

def test_code_single_use_and_not_long_link():
    code=admin.new_code(pair=True)
    assert c.post('/v1/pair',json={'code':code}).status_code==200
    assert c.post('/v1/pair',json={'code':code}).status_code==401
    assert c.post('/v1/pair',json={'code':admin.new_code()}).status_code==422

def test_sessions_persist_history():
    h=auth();sid=c.post('/v1/sessions',headers=h,json={'provider':'claude'}).json()['id']
    wappai.store.message(sid,'user','שלום Wappai 123')
    newer=c.post('/v1/sessions',headers=h,json={'provider':'claude'}).json()['id']
    assert newer!=sid
    assert c.post(f'/v1/sessions/{sid}/select',headers=h,json={}).status_code==200
    assert c.get('/v1/snapshot',headers=h).json()['messages'][0]['text']=='שלום Wappai 123'

def test_pip_validation_and_offline_truth():
    h=auth()
    for body in [{'name':'X','rig':99,'color':1},{'name':'X','rig':True,'color':1},{'name':'X','rig':1,'color':-1}]:
        assert c.post('/v1/pips',headers=h,json=body).status_code==422
    r=c.post('/v1/pips',headers=h,json={'name':'מנטה','rig':0,'color':0x80f2cd});assert r.status_code==200
    assert c.post('/v1/pips/'+r.json()['id']+'/activate',headers=h,json={}).status_code==409

def test_event_cursor_and_message_upsert():
    store=wappai.Store(':memory:');sid=store.session();a=store.event({'type':'a'});b=store.event({'type':'b'})
    assert store.events(a['cursor'])==[b]
    store.message(sid,'assistant','שלום','m');store.message(sid,'assistant','שלום עולם','m')
    assert len(store.rows('SELECT * FROM messages'))==1
    assert store.rows('SELECT text FROM messages')[0]['text']=='שלום עולם'

def test_busy_session_conflict():
    class Busy:
        def done(self):return False
    hub.task=Busy()
    try:assert c.post('/v1/sessions',headers=auth(),json={'provider':'claude'}).status_code==409
    finally:hub.task=None

def test_settings_bounds():
    h=auth()
    assert c.post('/v1/settings',headers=h,json={'volume':101}).status_code==422
    assert c.post('/v1/settings',headers=h,json={'execute':'whoami'}).status_code==422

def test_token_expiry():
    store=wappai.Store(':memory:');token=store.issue();assert store.authorized(token)
    store.db.execute('UPDATE clients SET expires=0');store.db.commit();assert not store.authorized(token)


def test_idempotency_binds_text_and_session():
    h=auth();sid=c.post('/v1/sessions',headers=h,json={'provider':'claude'}).json()['id']
    key=uuid.uuid4().hex
    body={'text':'הודעה לבדיקה','idempotency_key':key}
    first=c.post(f'/v1/sessions/{sid}/messages',headers=h,json=body)
    assert first.status_code==200
    repeated=c.post(f'/v1/sessions/{sid}/messages',headers=h,json=body)
    assert repeated.status_code==200 and repeated.json()['duplicate'] is True
    assert c.post(f'/v1/sessions/{sid}/messages',headers=h,json={**body,'text':'טקסט אחר'}).status_code==409
    other=wappai.store.session('claude')
    assert c.post(f'/v1/sessions/{other}/messages',headers=h,json=body).status_code==409
    rows=wappai.store.rows('SELECT * FROM messages WHERE session_id=? AND role=?',(sid,'user'))
    assert len(rows)==1

def test_expression_store_validation_and_isolation():
    h=auth();path='/v1/pips/pip/expressions'
    assert c.get(path).status_code==401
    pose={'name':'סקרנות שקטה','gazeX':.5,'leftArm':1.2,'cue':'curious'}
    r=c.post(path,headers=h,json=pose);assert r.status_code==200
    saved=r.json();assert saved['eyeOpen']==1
    assert saved in c.get(path,headers=h).json()
    assert saved not in c.get('/v1/pips/nori/expressions',headers=h).json()
    for field,value in [('eyeOpen',True),('bounce',500),('cue','https://evil'),('execute','touch file')]:
        assert c.post(path,headers=h,json={**pose,field:value}).status_code==422
    assert c.post('/v1/pips/missing/expressions',headers=h,json=pose).status_code==404
    assert c.post(path+'/play',headers=h,json=pose).status_code==409
    assert c.post(path+'/'+saved['id']+'/delete',headers=h,json={}).status_code==200
    assert saved not in c.get(path,headers=h).json()

def test_expression_generator_has_no_tools_or_mcp():
    from app.pip_studio import ExpressionBrain,validate
    import pytest
    args=ExpressionBrain()._args()
    assert args[args.index('--tools')+1]==''
    assert args[args.index('--mcp-config')+1]=='{"mcpServers":{}}'
    assert '--strict-mcp-config' in args
    for bad in [float('inf'),float('nan'),-100]:
        with pytest.raises(ValueError):validate({'name':'bad','speed':bad})

def test_expression_preview_validates_before_invoking_model():
    h=auth()
    for brief in ['',None,'x'*601]:
        assert c.post('/v1/pips/pip/expressions/preview',headers=h,json={'description':brief}).status_code==422


def test_expression_requires_device_acknowledgement():
    h=auth();pose={'name':'שלום','rightArm':2,'cue':'hello'}
    class Board:kind='board'
    original=hub.emit;hub.conns={Board()};hub.receipts={}
    async def acknowledged(obj,**kwargs):
        if obj.get('type')=='pip.expression':hub.receipts[obj['id']].set_result({'status':'applied'})
    hub.emit=acknowledged
    try:
        r=c.post('/v1/pips/pip/expressions/play',headers=h,json=pose)
        assert r.status_code==200 and r.json()['status']=='applied'
        assert not hub.receipts
        async def busy(obj,**kwargs):hub.receipts[obj['id']].set_result({'status':'busy'})
        hub.emit=busy
        assert c.post('/v1/pips/pip/expressions/play',headers=h,json=pose).status_code==409
        assert not hub.receipts
    finally:hub.emit=original;hub.conns=set()

def test_pixel_motion_validation():
    from app.pip_studio import validate,MOTIONS
    for name in MOTIONS:
        assert validate({'name':'בדיקה','motion':name})['motion']==name
    assert validate({'name':'הבעה ישנה'})['motion']==''
    for bad in ['../../file','exec()',123,True,[],None]:
        try:validate({'name':'בדיקה','motion':bad})
        except ValueError:pass
        else:raise AssertionError('Unknown or non-string motion accepted')

def test_pixel_catalog_and_assets_agree():
    import json
    from pathlib import Path
    from PIL import Image
    root=Path(__file__).resolve().parents[2]
    catalog=json.loads((root/'assets/pips/pixel/catalog.json').read_text())
    for path in ['ios/Piko/Piko/PipMotions.json','server/sim/pixel-motions.json']:
        assert json.loads((root/path).read_text())==catalog
    for char in catalog['characters']:
        for frame in range(len(catalog['poses'])):
            image=Image.open(root/f'server/sim/pixel-{char["id"]}-{frame}.png')
            assert image.size==(96,96) and image.mode=='RGBA'
            bounds=image.getchannel('A').getbbox()
            assert bounds and 0<bounds[0]<bounds[2]<96 and 0<bounds[1]<bounds[3]<96
    for frames in catalog['motions'].values():
        assert frames and all(0<=f['pose']<len(catalog['poses']) and 80<=f['ms']<=10000 for f in frames)


def test_context_is_durable_bounded_and_session_scoped(monkeypatch,tmp_path):
    store=wappai.Store(tmp_path/'context.db');a=store.session();b=store.session()
    store.message(a,'user','אני בוחר בסגול');store.message(a,'assistant','איזה גודל תרצה?')
    store.message(a,'user','קטן');store.message(b,'user','סוד משיחה אחרת')
    monkeypatch.setattr(wappai,'store',store)
    context=wappai.conversation_context('קטן',a)
    assert 'סגול' in context and 'איזה גודל' in context and 'קטן' not in context and 'סוד' not in context
    # Reloaded storage still supplies the same follow-up history.
    monkeypatch.setattr(wappai,'store',wappai.Store(tmp_path/'context.db'))
    assert wappai.conversation_context('קטן',a)==context
    for i in range(40):store.message(a,'user','x'*4000)
    assert len(wappai.conversation_context('',a))<17000

def test_active_session_selection_is_persisted():
    h=auth();sid=c.post('/v1/sessions',headers=h,json={'provider':'claude'}).json()['id']
    assert c.post('/v1/sessions/'+sid+'/select',headers=h,json={}).status_code==200
    assert wappai.store.rows("SELECT value FROM app_meta WHERE key='active_session'")[0]['value']==sid

def test_shake_setting_boolean_validation():
    h=auth()
    assert c.post('/v1/settings',headers=h,json={'shake_reaction':False}).status_code==200
    assert c.get('/v1/snapshot',headers=h).json()['settings']['shake_reaction'] is False
    assert c.post('/v1/settings',headers=h,json={'shake_reaction':1}).status_code==422


def test_live_partial_is_ephemeral_and_reaches_client():
    h=auth();before=wappai.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    cursor=wappai.store.db.execute('SELECT COALESCE(MAX(cursor),0) FROM events').fetchone()[0]
    with TestClient(app) as live:
        with live.websocket_connect(f'/v1/events?after={cursor}',headers=h) as ws:
            live.portal.call(wappai.observe,{'type':'transcript.partial','text':'תמלול חי'})
            event=ws.receive_json()
            assert event['type']=='transcript.partial' and event['text']=='תמלול חי' and 'cursor' not in event
            assert wappai.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==before
