"""Validate the public board catalog without connecting to or flashing a device."""
import hashlib,json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'release/firmware-catalog.json').read_text())
assert catalog['schema_version']==1 and catalog['repository']=='rotem221/Wappai'
expected={'ws-s3-175c','ws-s3-175','ws-s3-18','ws-s3-216'}
assert len(catalog['boards'])==len(expected) and {b['id'] for b in catalog['boards']}==expected
for board in catalog['boards']:
 release=board['release']
 if board['status']!='available':
  assert release is None, 'Unvalidated boards must not expose binaries'
  continue
 assert board['id']=='ws-s3-175c', 'Additional boards need a reviewed BSP and hardware validation before enabling distribution'
 assert release['update_method']=='usb', 'OTA is not approved by the current hardware qualification'
 assert re.fullmatch(r'[a-f0-9]{64}',release['sha256'])
 assert release['install_url'].endswith('?board='+board['id'])
 image=root/'site/firmware'/release['factory_file'];data=image.read_bytes()
 assert len(data)==release['bytes'] and hashlib.sha256(data).hexdigest()==release['sha256']
 assert data[0]==0xe9 and int.from_bytes(data[12:14],'little')==9
 assert release['version'].encode()+b'\0' in data, 'Published image must contain its advertised firmware version'
 if (root/'release/firmware/manifest.json').exists():
  for part in json.loads((root/'release/firmware/manifest.json').read_text())['parts']:
   part_data=(root/'release/firmware'/part['file']).read_bytes();start=int(part['offset'],16)
   assert hashlib.sha256(part_data).hexdigest()==part['sha256']
   assert data[start:start+len(part_data)]==part_data
 print(board['id'], release['package_version'], 'image, parts, version and board verified')
print('Unvalidated boards are blocked; no board-family fallback; no automatic OTA publication')
