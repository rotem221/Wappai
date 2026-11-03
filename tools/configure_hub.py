"""Configure your own Hub over USB without putting credentials in shell history."""
import argparse,getpass,time
from urllib.parse import urlsplit
import serial
p=argparse.ArgumentParser();p.add_argument('--port',required=True);args=p.parse_args()
url=input('Hub WebSocket URL (wss://your-hub/ws): ').strip()
u=urlsplit(url)
if u.scheme!='wss' or not u.hostname or u.username or u.password or len(url)>160:raise SystemExit('Enter a valid wss:// Hub URL, at most 160 characters.')
token=getpass.getpass('Your Hub DEVICE_TOKEN: ').strip()
if not 24<=len(token)<=128 or any(c.isspace() for c in token):raise SystemExit('The token must contain 24–128 characters with no whitespace.')
with serial.Serial(args.port,115200,timeout=.2) as device:
 time.sleep(2)
 for command in ('url '+url,'token '+token,'reboot'):
  device.write((command+'\n').encode());device.flush();time.sleep(.5)
print('Hub settings saved. Pair Wi-Fi through Wappai on iOS, then connect the app to the same Hub.')
