"""Isolated production-turn regression: no appliances, account, or model calls."""
import asyncio, os, sys, tempfile
from pathlib import Path
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='wappai-voice-turn-')
os.environ['COMPANION_ENV']='/nonexistent';os.environ['BRAIN']='claude_cli'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server'))
from app import main
from unittest.mock import AsyncMock

async def run():
    events=[]
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
    events.clear();await main.converse('מה מזג האוויר?',heard=False)
    assert any(e.get('kind')=='weather' for e in events)
    print('Production conversation: air conditioner never opens weather; pending and verified room badge, textual thinking and explicit weather all passed.')
asyncio.run(run())
