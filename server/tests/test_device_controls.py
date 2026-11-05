import asyncio,json,types
import pytest
from app.device_controls import parse,apply

@pytest.mark.parametrize('text,key,value',[
 ('תוריד את הבהירות ל30 אחוז','brightness',76),('תגדיר בהירות למאה אחוז','brightness',255),
 ('הנמך את הווליום','volume',70),('אפשר להגביר מעט את הווליום?','volume',90),
 ('תגדיר עוצמת קול ל0','volume',0),('הורד ווליום ב10 אחוז','volume',70),
 ('תעלה את הבהירות','brightness',196),('תגדיר בהירות ל0 אחוז','brightness',20),
])
def test_commands(text,key,value):assert parse(text,{'brightness':170,'volume':80})=={key:value}
@pytest.mark.parametrize('text',[
 'אל תנמיך את הווליום','הוא אמר להגביר את הווליום','למה הבהירות ירדה?','מה זה ווליום',
 'תגביר את המוזיקה ברמקול בסלון','תוריד ווליום ל150 אחוז','תעלה ותוריד בהירות',
 'הגבר בהירות ועוצמה','אמרתי "תנמיך את הקול"','תגדיר את הבהירות','בפגישה דיברו בקול חלש',
])
def test_no_unintended_controls(text):assert parse(text,{}) is None

@pytest.mark.parametrize('status',['applied','busy','offline'])
def test_receipt_before_persistence(tmp_path,status):
 f=tmp_path/'settings.json';f.write_text('{"volume":80,"owner":"unchanged"}')
 admin=types.SimpleNamespace(settings=lambda:json.loads(f.read_text()),SETTINGS_FILE=f,apply_settings=lambda:None,current_settings=lambda:json.loads(f.read_text()))
 hub=types.SimpleNamespace(receipts={},conns=[] if status=='offline' else [types.SimpleNamespace(kind='board')]);events=[]
 async def send(payload,**kw):
  assert json.loads(f.read_text())['volume']==80
  hub.receipts[payload['command_id']].set_result({'status':status})
 async def emit(event):events.append(event)
 hub.emit=send
 reply=asyncio.run(apply('תנמיך ווליום',hub,admin,emit))
 assert bool(reply) and not hub.receipts
 assert json.loads(f.read_text())=={'volume':70 if status=='applied' else 80,'owner':'unchanged'}
 assert len(events)==(1 if status=='applied' else 0)
