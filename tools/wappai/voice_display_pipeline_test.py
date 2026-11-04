"""Isolated production-turn regression: no appliances, account, or model calls."""
import asyncio, os, sys, tempfile
from pathlib import Path
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='wappai-voice-turn-')
os.environ['COMPANION_ENV']='/nonexistent';os.environ['BRAIN']='claude_cli'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server'))
from app import main
from unittest.mock import AsyncMock

async def run():
    events=[];contexts=[]
    main.config.USER_ADDRESS="auto"
    async def emit(obj=None,binary=None,**kw):
        if obj:events.append(obj)
    main.hub.emit=emit
    main.context.build=AsyncMock(return_value='')
    main.context.weather=AsyncMock(return_value='')
    main.context.weather_data=lambda:{'t':25}
    main.ha.configured=lambda:True
    ac={'id':'climate.playroom','name':'מזגן חדר משחקים','kind':'climate','on':False,'available':True,'state':'כבוי'}
    main.ha.entities=AsyncMock(return_value=[ac,dict(ac,id='climate.bedroom',name='מזגן חדר שינה')])
    main.ha.state=AsyncMock(return_value={'entity_id':'climate.playroom','state':'off','attributes':{'friendly_name':ac['name']}})
    async def speech(*a,**kw):yield bytes(2048)
    main.tts.stream=speech
    class Brain:
        async def ask(self,*a):
            contexts.append(a[1])
            # Deliberately wrong model card is suppressed for a home-only request.
            yield '[happy]<show what="weather"/><show what="device" entity="climate.playroom"/>המזגן כבוי.'
    main.wappai.current_brain=lambda:Brain()
    await main.converse('תכבה את המזגן בחדר משחקים',heard=False)
    assert not any(e.get('kind')=='weather' for e in events),events
    badges=[e for e in events if e['type']=='device.badge']
    assert badges[0]['pending'] and not badges[-1]['pending']
    assert all(e['dev']['id']=='climate.playroom' for e in badges)
    assert events[-1]['type']=='turn.completed'
    assert events[0]['type']=='interaction' and events[0]['clear_card']
    assert any(e.get('text')==main.preferences.QUESTION for e in events)
    main.wappai.store.message(main.wappai.active,'assistant',main.preferences.QUESTION)
    events.clear();await main.converse('נקבה',heard=False)
    assert main.config.USER_ADDRESS=='feminine'
    assert 'את, תרצי, יכולה' in contexts[-1]
    assert not any(e.get('text')==main.preferences.QUESTION for e in events)
    events.clear();await main.converse('מה מזג האוויר?',heard=False)
    assert any(e.get('kind')=='weather' for e in events)
    import types
    started=asyncio.Event();both=asyncio.Event()
    async def recognize(pcm):
        started.set();await both.wait();return ('en','Hello, this is English.')
    class Session:
        async def finish(self):
            await started.wait();both.set();return 'תמלול עברי'
    sys.modules['app.voice.stt_fast']=types.SimpleNamespace(recognize=recognize)
    main.config.STT_ENGINE='hybrid';main.converse=AsyncMock()
    await asyncio.wait_for(main.handle_audio(bytes(32000),Session()),2)
    assert main.converse.call_args.args[0]=='Hello, this is English.'
    print('Production conversation: air conditioner never opens weather; pending and verified room badge, textual thinking and explicit weather all passed.')
asyncio.run(run())
