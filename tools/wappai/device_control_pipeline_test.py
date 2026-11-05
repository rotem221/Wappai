"""Exercise the production voice response path with a receipt and synthetic PCM only."""
import asyncio,os,sys,tempfile,types
from pathlib import Path
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='wappai-controls-voice-');os.environ['COMPANION_ENV']='/nonexistent'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'server'))
from app import main
from unittest.mock import AsyncMock
async def run():
 events=[];pcm=[];main.hub.conns={types.SimpleNamespace} # replaced below with a hashable board
 main.hub.conns={type('Board',(),{'kind':'board'})()}
 async def emit(obj=None,binary=None,**kwargs):
  if obj:
   events.append(obj)
   if obj.get('type')=='config':main.hub.receipts[obj['command_id']].set_result({'status':'applied','effective_brightness':obj.get('brightness',255)})
  if binary:pcm.append(binary)
 main.hub.emit=emit;main.wappai.emit=AsyncMock();main.context.build=AsyncMock(side_effect=AssertionError('No slow context for local controls'))
 class Brain:
  async def ask(self,*a):raise AssertionError('No model round-trip for direct controls');yield ''
 main.wappai.current_brain=lambda:Brain()
 async def tts(*a):yield bytes(3200)
 main.tts.stream=tts
 await main.converse('תגדיר בהירות ל30 אחוז',heard=False)
 assert not any(e['type']=='turn.failed' for e in events)
 assert events[-1]['type']=='turn.completed'
 assert [e for e in events if e['type']=='config'][0]['brightness']==76
 assert any('30' in e.get('text','') for e in events if e['type']=='say')
 assert len(b''.join(pcm))==3200 and not main.hub.receipts
 assert not any(e.get('text')==main.preferences.QUESTION for e in events)
 print('Production control receipt → Hebrew confirmation → PCM playback passed; no model/context round-trip')
asyncio.run(run())
