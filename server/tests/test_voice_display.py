import asyncio
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app import config, admin
from app.display_intent import weather_requested, requested_device
from app.voice import elevenlabs, settings as voice_settings, tts, stt_stream

@pytest.mark.parametrize('text',["תדליק את המזגן בחדר משחקים","תכבה את המזגן","שים מזגן על עשרים מעלות","מה הטמפרטורה במזגן?","Turn off the air conditioner"])
def test_air_conditioning_is_not_weather(text):assert not weather_requested(text)
@pytest.mark.parametrize('text',["מה מזג האוויר?","מה מזג האויר?","תחזית למחר","כמה מעלות בחוץ?","What's the weather?","תכבה מזגן וגם מה מזג האוויר?"])
def test_weather_intent(text):assert weather_requested(text)

def test_device_unique_room_not_auxiliary_switch():
    ac={'id':'climate.playroom','name':'מזגן חדר משחקים','kind':'climate'}
    items=[ac,{'id':'switch.react','name':'מזגן חדר משחקים Climate React','kind':'switch'}, {'id':'climate.bedroom','name':'מזגן חדר שינה','kind':'climate'}]
    assert requested_device('תדליק את המזגן בחדר משחקים',items)==ac
    assert requested_device('כבה את המזגן בחדר המשחקים',items)==ac
    assert requested_device('כבה את המזגן',items) is None
    assert requested_device('כבה מזגן חדר משחקים',items+[dict(ac,id='climate.other')]) is None

def test_lively_voice_respects_empathy(monkeypatch):
    monkeypatch.setattr(config,'TTS_STYLE','natural');neutral=tts._prosody('speaking');sad=tts._prosody('sad')
    monkeypatch.setattr(config,'TTS_STYLE','lively');assert tts._prosody('speaking')!=neutral;assert tts._prosody('sad')==sad
    assert elevenlabs.speech_body('שלום','happy','eleven_v3','lively')['text'].startswith('[excited]')
    assert elevenlabs.speech_body('מצטער','sad','eleven_v3','lively')['text']=='מצטער'

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setattr(elevenlabs,'SECRET_FILE',tmp_path/'elevenlabs.json');monkeypatch.setattr(admin,'SETTINGS_FILE',tmp_path/'settings.json')
    for name,value in [('ELEVENLABS_API_KEY',''),('ELEVENLABS_VOICE_ID',''),('ELEVENLABS_MODEL','eleven_v3'),('TTS_PROVIDER','edge'),('TTS_STYLE','lively')]:monkeypatch.setattr(config,name,value)
    app=FastAPI()
    def require(request):
        if request.headers.get('Authorization')!='Bearer test':raise HTTPException(401)
    voice_settings.register(app,require);return TestClient(app)
H={'Authorization':'Bearer test'}

def test_voice_auth_and_missing_account(client):
    assert client.get('/v1/voice').status_code==401
    assert client.get('/v1/voice',headers=H).json()['connected'] is False
    assert client.post('/v1/voice',headers=H,json={'provider':'elevenlabs','voice_id':'abc','model_id':'eleven_v3'}).status_code==409
    assert client.post('/v1/voice',headers=H,json={'provider':'edge','style':'lively','edge_voice':'he-IL-HilaNeural'}).status_code==200

def test_connect_search_select_preview_secret_redaction(client,monkeypatch):
    calls=[]
    async def get(path,api_key=None,params=None):
        calls.append((path,params))
        if path=='/v1/models':return [{'model_id':'eleven_v3','name':'Expressive','can_do_text_to_speech':True,'languages':[{'language_id':'he'}]}, {'model_id':'no_hebrew','can_do_text_to_speech':True,'languages':[{'language_id':'en'}]}]
        if path=='/v2/voices':return {'voices':[{'voice_id':'voice123','name':'Test','labels':{'language':'he'}}],'has_more':True,'next_page_token':'page2'}
        return {'voice_id':'voice123'}
    monkeypatch.setattr(elevenlabs,'get',get)
    secret='not-a-real-api-key-for-test'
    result=client.post('/v1/voice/connect',headers=H,json={'api_key':secret})
    assert result.status_code==200 and secret not in result.text
    assert elevenlabs.SECRET_FILE.stat().st_mode & 0o777==0o600 and elevenlabs.key()==secret
    result=client.post('/v1/voice/search',headers=H,json={'search':'Test','cursor':'page2'})
    assert result.status_code==200 and result.json()['next_cursor']=='page2'
    assert ('/v2/voices',{'page_size':50,'include_total_count':False,'search':'Test','next_page_token':'page2'}) in calls
    body={'provider':'elevenlabs','voice_id':'voice123','model_id':'eleven_v3','style':'lively'}
    assert client.post('/v1/voice',headers=H,json=body).status_code==200
    admin.apply_settings();assert config.TTS_PROVIDER=='elevenlabs' and config.ELEVENLABS_VOICE_ID=='voice123'
    assert client.post('/v1/voice',headers=H,json={**body,'model_id':'no_hebrew'}).status_code==422
    async def stream(*args,**kwargs):yield b'\x00\x00'*1600
    monkeypatch.setattr(elevenlabs,'stream',stream)
    result=client.post('/v1/voice/preview',headers=H,json=body)
    assert result.status_code==200 and result.content[:4]==b'RIFF'
    assert secret not in client.get('/v1/voice',headers=H).text

def test_invalid_key_keeps_old_key(client,monkeypatch):
    elevenlabs.save_key('previous-test-key')
    async def failure(*args,**kwargs):raise httpx.HTTPStatusError('secret text',request=httpx.Request('GET','https://api.elevenlabs.io/v2/voices'),response=httpx.Response(401))
    monkeypatch.setattr(elevenlabs,'voices',failure)
    result=client.post('/v1/voice/connect',headers=H,json={'api_key':'new-test-key-invalid'})
    assert result.status_code==422 and 'secret text' not in result.text and elevenlabs.key()=='previous-test-key'

def test_stream_partial_before_release(monkeypatch):
    class Recognizer:
        def create_stream(self):return object()
    monkeypatch.setattr(stt_stream,'_recognizer',lambda:Recognizer())
    monkeypatch.setattr(stt_stream.Session,'_feed',lambda self,pcm:'מזגן חדר משחקים')
    monkeypatch.setattr(stt_stream.Session,'_finish',lambda self:'תדליק מזגן חדר משחקים')
    async def run():
        heard=[];ready=asyncio.Event()
        async def partial(text):heard.append(text);ready.set()
        session=stt_stream.Session(on_partial=partial);session.feed(b'\x00\x00'*3200)
        await asyncio.wait_for(ready.wait(),2)
        assert not session.worker.done() and heard==['מזגן חדר משחקים']
        session.feed(b'\x00\x00'*3200)
        assert await session.finish()=='תדליק מזגן חדר משחקים' and len(heard)==1
    asyncio.run(run())

@pytest.mark.parametrize('payload,valid',[(b'\x01\x00\x02\x00',True),(b'\x01\x00\x02',False),(b'',False)])
def test_elevenlabs_pcm_contract_and_voice_options(monkeypatch,payload,valid):
    real_client=httpx.AsyncClient;requests=[]
    def respond(request):
        import json
        requests.append((str(request.url),json.loads(request.content)))
        return httpx.Response(200,content=payload)
    monkeypatch.setattr(elevenlabs,'key',lambda:'fake-private-key')
    monkeypatch.setattr(elevenlabs.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(respond),**kwargs))
    async def run():
        chunks=[]
        async for chunk in elevenlabs.stream('שלום','happy',voice_id='voice123',model='eleven_v3',style='lively'):chunks.append(chunk)
        return b''.join(chunks)
    if valid:assert asyncio.run(run())==payload
    else:
        with pytest.raises(RuntimeError):asyncio.run(run())
    assert requests[0][0].endswith('/voice123/stream?output_format=pcm_16000')
    assert requests[0][1]['model_id']=='eleven_v3' and requests[0][1]['text'].startswith('[excited]')
