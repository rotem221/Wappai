import asyncio
import json
import wave
from pathlib import Path
import pytest
from test_wappai import app,auth,hub
from fastapi.testclient import TestClient
from app import meeting_storage
from app.tools import meeting
from app.notifications import Notifications

c=TestClient(app)

def test_library_auth_capacity_and_recording_consent():
    assert c.get('/v1/meetings').status_code==401
    h=auth();r=c.get('/v1/meetings',headers=h)
    assert r.status_code==200 and r.json()['capacity']['remaining_seconds']>=0
    assert c.post('/v1/meetings/start',headers=h,json={}).status_code==422
    assert c.post('/v1/meetings/start',headers=h,json={'consent':True}).status_code==409
    assert c.get('/v1/meetings/not-a-file',headers=h).status_code==404
    assert c.post('/v1/notifications/register',headers=h,json={'installation':'x','token':'y'}).status_code==422

def test_duplicate_audio_and_capacity_stop_preserve_audio(tmp_path,monkeypatch):
    monkeypatch.setattr(meeting,'DIR',tmp_path)
    monkeypatch.setattr(meeting.stt_stream,'available',lambda:False)
    monkeypatch.setattr(meeting_storage,'capacity',lambda:{'remaining_seconds':100,'cloud_configured':False})
    monkeypatch.setattr(meeting,'_encode',lambda path:None)
    from app.voice import stt
    async def empty(pcm):return ''
    monkeypatch.setattr(stt,'transcribe',empty)
    async def run():
        mt=meeting.Meeting('123-456')
        pcm=b'\x01\x00'*16000
        mt.feed_sequenced(0,pcm);mt.feed_sequenced(0,pcm)
        assert mt.meta['seconds']==1
        with pytest.raises(ValueError):mt.feed_sequenced(2,pcm)
        mt.budget=0;mt.last_budget_check=__import__('time').monotonic()
        with pytest.raises(OSError):mt.feed_sequenced(1,pcm)
        await mt.finish()
        assert mt.meta['state']=='audio_only' and mt.meta['stop_reason']=='storage_limit'
        with wave.open(str(tmp_path/'123-456'/'part-001.wav')) as audio:assert audio.getnframes()==16000
        assert meeting.audio_file('123-456').suffix=='.wav'
        assert meeting._safe_dir('../123') is None
        assert meeting.delete(mt.id) is False  # Summary/deletion guard remains held.
        mt.cancel()
    asyncio.run(run())

def test_no_incomplete_concat(tmp_path):
    (tmp_path/'part-001.m4a').write_bytes(b'encoded')
    (tmp_path/'part-002.wav').write_bytes(b'failed')
    (tmp_path/'audio.m4a').write_bytes(b'stale complete prefix')
    assert meeting._concat(tmp_path) is None
    assert not (tmp_path/'audio.m4a').exists()

def test_cloud_upload_failure_never_evicts_local(tmp_path,monkeypatch):
    path=tmp_path/'audio.m4a';path.write_bytes(b'audio')
    monkeypatch.setenv('MEETING_CLOUD_EVICT','1')
    meeting_storage.evict(tmp_path);assert path.exists()
    monkeypatch.setenv('MEETING_S3_BUCKET','private-test')
    class Fake:
        def upload_file(self,*a,**k):raise OSError('offline')
    monkeypatch.setattr(meeting_storage,'client',Fake)
    with pytest.raises(OSError):meeting_storage.archive(path)
    assert path.exists() and not (tmp_path/'audio.cloud.json').exists()

def test_cloud_verified_upload_and_delete(tmp_path,monkeypatch):
    import hashlib
    path=tmp_path/'audio.m4a';path.write_bytes(b'audio');deleted=[]
    monkeypatch.setenv('MEETING_S3_BUCKET','private-test')
    class Fake:
        def upload_file(self,*a,**k):pass
        def head_object(self,**kw):return {'ContentLength':5,'Metadata':{'sha256':hashlib.sha256(b'audio').hexdigest()}}
        def delete_object(self,**kw):deleted.append(kw['Key'])
    monkeypatch.setattr(meeting_storage,'client',Fake)
    receipt=meeting_storage.archive(path);assert receipt['bytes']==5
    meeting_storage.delete_archive(tmp_path);assert deleted==[receipt['key']]


@pytest.mark.parametrize('failure',['bucket_changed','remote_missing','remote_changed','local_changed','no_transcript','none'])
def test_cloud_eviction_revalidates_final_archive(tmp_path,monkeypatch,failure):
    import hashlib
    audio=tmp_path/'audio.m4a';audio.write_bytes(b'audio')
    transcript=tmp_path/'transcript.txt';transcript.write_text('Test transcript')
    digest=hashlib.sha256(b'audio').hexdigest()
    receipt={'bucket':'private-test','key':'meetings/'+tmp_path.name+'/audio.m4a','sha256':digest,'bytes':5}
    audio.with_suffix('.cloud.json').write_text(json.dumps(receipt))
    monkeypatch.setenv('MEETING_CLOUD_EVICT','1');monkeypatch.setenv('MEETING_S3_BUCKET','private-test')
    class Fake:
        def head_object(self,**kwargs):
            if failure=='remote_missing':raise OSError('Object no longer exists')
            return {'ContentLength':5,'Metadata':{'sha256':'wrong' if failure=='remote_changed' else digest}}
    monkeypatch.setattr(meeting_storage,'client',Fake)
    if failure=='bucket_changed':monkeypatch.setenv('MEETING_S3_BUCKET','different-bucket')
    if failure=='local_changed':audio.write_bytes(b'other')
    if failure=='no_transcript':transcript.unlink()
    meeting_storage.evict(tmp_path)
    assert audio.exists()==(failure!='none')
    if failure=='none':assert transcript.exists() and audio.with_suffix('.cloud.json').exists()

def test_push_dedupe_opt_out_and_retry(tmp_path,monkeypatch):
    svc=Notifications(tmp_path/'push.sqlite')
    svc.register('installation-123456','ab'*32,'sandbox',True,True)
    svc.enqueue('meetings','meeting-1','123-456');svc.enqueue('meetings','meeting-1','123-456')
    assert svc.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    payload=json.loads(svc.db.execute('SELECT body FROM outbox').fetchone()[0]);assert 'transcript' not in payload
    monkeypatch.setattr(svc,'configured',lambda:True)
    async def fail(*args):return 503,'ServiceUnavailable'
    monkeypatch.setattr(svc,'send',fail);asyncio.run(svc.drain())
    row=svc.db.execute('SELECT * FROM outbox').fetchone();assert row['state']=='pending' and row['attempts']==1
    svc.db.execute('UPDATE outbox SET due=0');svc.db.commit()
    async def bad(*args):return 410,'Unregistered'
    monkeypatch.setattr(svc,'send',bad);asyncio.run(svc.drain())
    assert svc.db.execute('SELECT COUNT(*) FROM devices').fetchone()[0]==0
    assert svc.db.execute('SELECT state FROM outbox').fetchone()[0]=='invalid_token'

def test_push_offline_and_permissions(tmp_path):
    svc=Notifications(tmp_path/'push.sqlite')
    svc.register('installation-123456','ab'*32,'production',False,True)
    svc.enqueue('timers','timer-1');assert svc.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==0
    with pytest.raises(ValueError):svc.register('installation-123456','ab'*32,'bad',True,True)
    assert c.get('/v1/notifications').status_code==401


def test_recovery_rolls_back_unacknowledged_block(tmp_path,monkeypatch):
    monkeypatch.setattr(meeting,'DIR',tmp_path)
    monkeypatch.setattr(meeting,'_encode',lambda p:None)
    directory=tmp_path/'123-789';directory.mkdir()
    (directory/'meta.json').write_text(json.dumps({'id':'123-789','state':'recording','seconds':2,'last_seq':0}))
    (directory/'pending-block.json').write_text(json.dumps({'seq':1,'seconds':1,'part_n':1,'part_bytes':32000,'open':True}))
    with wave.open(str(directory/'part-001.wav'),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(b'\0'*64000)
    meeting.recover()
    m=json.loads((directory/'meta.json').read_text())
    assert m['seconds']==1 and m['state']=='interrupted' and m['last_seq']==0
    with wave.open(str(directory/'part-001.wav')) as audio:assert audio.getnframes()==16000


def test_partial_audio_exposes_all_parts_not_false_complete(tmp_path,monkeypatch):
    monkeypatch.setattr(meeting,'DIR',tmp_path)
    directory=tmp_path/'123-456';directory.mkdir()
    (directory/'part-001.m4a').write_bytes(b'one')
    (directory/'part-002.wav').write_bytes(b'two')
    assert meeting.audio_file('123-456') is None
    assert len(meeting.audio_parts('123-456'))==2


def test_invalid_adpcm_index():
    from app.voice.adpcm import decode
    with pytest.raises(ValueError):decode(b'\0\0\xff\0\0')


def test_long_meeting_summary_covers_middle_when_live_summary_missing(tmp_path,monkeypatch):
    monkeypatch.setattr(meeting,'DIR',tmp_path)
    monkeypatch.setattr(meeting.stt_stream,'available',lambda:False)
    async def run():
        mt=meeting.Meeting('123-999');text='a'*7000+'MIDDLE-DECISION'+'b'*14000
        mt.transcript.write_text(text);seen=[]
        async def summarize(prompt,model):seen.append(prompt);return 'summary '+str(len(seen))
        source=await mt.prepare_summary_source(summarize)
        assert any('MIDDLE-DECISION' in prompt for prompt in seen)
        assert mt.meta['chunk_from']>=len(text)-6000 and 'summary 1' in source
        mt.cancel()
    asyncio.run(run())


def test_apns_signed_request_and_environment(tmp_path,monkeypatch):
    import jwt,httpx
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key=ec.generate_private_key(ec.SECP256R1());pem=tmp_path/'apns-test.p8'
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    for name,value in {'APNS_KEY_ID':'TESTKEY','APNS_TEAM_ID':'TESTTEAM','APNS_KEY_FILE':str(pem),'APNS_TOPIC':'test.wappai'}.items():monkeypatch.setenv(name,value)
    svc=Notifications(tmp_path/'request.sqlite');svc.register('installation-123456','ab'*32,'sandbox',True,True);svc.enqueue('timers','verified-event')
    calls=[]
    class Client:
        def __init__(self,**kwargs):assert kwargs['http2'] is True
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,content,headers):
            calls.append(url);assert url.startswith('https://api.sandbox.push.apple.com/3/device/')
            assert headers['apns-topic']=='test.wappai' and headers['apns-push-type']=='alert'
            claims=jwt.decode(headers['authorization'][7:],key.public_key(),algorithms=['ES256'])
            assert claims['iss']=='TESTTEAM'
            assert json.loads(content)['kind']=='timers'
            return httpx.Response(200)
    monkeypatch.setattr(httpx,'AsyncClient',Client);asyncio.run(svc.drain())
    assert len(calls)==1 and svc.db.execute('SELECT state FROM outbox').fetchone()[0]=='sent'
    asyncio.run(svc.drain());assert len(calls)==1


def test_apns_scoped_keys_cache_connections_and_rotation(tmp_path,monkeypatch):
    import jwt,httpx
    from app import notifications
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    keys={}
    for env in ('sandbox','production'):
        key=ec.generate_private_key(ec.SECP256R1());keys[env]=key
        path=tmp_path/(env+'.p8')
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        monkeypatch.setenv('APNS_'+env.upper()+'_KEY_ID',env.upper())
        monkeypatch.setenv('APNS_'+env.upper()+'_KEY_FILE',str(path))
    monkeypatch.setenv('APNS_TEAM_ID','TESTTEAM');monkeypatch.setenv('APNS_TOPIC','test.wappai')
    monkeypatch.setenv('APNS_KEY_FILE',str(tmp_path/'missing-legacy'))
    svc=Notifications(tmp_path/'scoped.sqlite');clients=[];calls=[]
    clock=[1700000000];monkeypatch.setattr(notifications.time,'time',lambda:clock[0])
    class Client:
        def __init__(self,**kwargs):self.closed=False;clients.append(self)
        async def aclose(self):self.closed=True
        async def post(self,url,content,headers):
            env='sandbox' if 'sandbox' in url else 'production'
            token=headers['authorization'][7:]
            assert jwt.get_unverified_header(token)['kid']==env.upper()
            claims=jwt.decode(token,keys[env].public_key(),algorithms=['ES256'],options={'verify_iat':False})
            assert claims['iss']=='TESTTEAM'
            calls.append((env,token,self));return httpx.Response(200)
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    row={'body':'{}','expires':clock[0]+3600,'id':'test'}
    async def run():
        for env in ('sandbox','sandbox','production'):
            assert await svc.send(row,{'environment':env,'token':'ab'*32})==(200,'')
        assert len(clients)==2 and calls[0][1:]==calls[1][1:]
        clock[0]+=2999
        await svc.send(row,{'environment':'sandbox','token':'ab'*32})
        assert calls[-1][1]==calls[0][1]
        clock[0]+=1
        await svc.send(row,{'environment':'sandbox','token':'ab'*32})
        assert calls[-1][1]!=calls[0][1] and len(clients)==2
        # A partial scoped configuration must never fall back to another key.
        monkeypatch.delenv('APNS_PRODUCTION_KEY_FILE')
        assert svc.configured('sandbox') and not svc.configured('production')
        assert await svc.send(row,{'environment':'production','token':'ab'*32})==(503,'EnvironmentNotConfigured')
        assert len(calls)==5
        # Replacing a key starts a fresh connection; other environments stay separate.
        path=tmp_path/'sandbox-rotated.p8'
        path.write_bytes((tmp_path/'sandbox.p8').read_bytes())
        monkeypatch.setenv('APNS_SANDBOX_KEY_FILE',str(path))
        await svc.send(row,{'environment':'sandbox','token':'ab'*32})
        assert len(clients)==3 and clients[0].closed
        await svc.close()
        assert all(client.closed for client in clients)
    asyncio.run(run())


def test_pip_notification_migrates_existing_preferences_and_opt_out(tmp_path,monkeypatch):
    import sqlite3
    path=tmp_path/'legacy-push.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE devices(id TEXT PRIMARY KEY,token TEXT,environment TEXT,timers INTEGER,meetings INTEGER,updated REAL)')
    svc=Notifications(path)
    svc.register('installation-123456','ab'*32,'sandbox',True,True)
    svc.enqueue('pips','preview','job',stage='preview_ready')
    assert svc.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==0
    svc.register('installation-123456','ab'*32,'sandbox',True,True,True)
    svc.enqueue('pips','preview','job',stage='preview_ready')
    svc.enqueue('pips','preview','job',stage='preview_ready')
    assert svc.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    svc.register('installation-123456','ab'*32,'sandbox',True,True,False)
    monkeypatch.setattr(svc,'configured',lambda:True)
    asyncio.run(svc.drain())
    assert svc.db.execute('SELECT state FROM outbox').fetchone()[0]=='cancelled'
    with pytest.raises(ValueError):svc.register('installation-123456','ab'*32,'sandbox',True,True,'yes')
