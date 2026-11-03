"""Flash app0 only after verifying the known device's recovery image and partition table.
For this particular USB board only; not a general-purpose release flasher.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
recovery=Path.home()/'.local/share/wappai/recovery/2026-11-03'
manifest=json.loads((recovery/'manifest.json').read_text())
backup=(recovery/'piko-0.4.5-full-32mb.bin').read_bytes()
assert len(backup)==manifest['flash_bytes']
assert hashlib.sha256(backup).hexdigest()==manifest['sha256']
assert 'Hash of data verified' in (recovery/'verify-flash.log').read_text() or 'verify OK' in (recovery/'verify-flash.log').read_text()
build=repo/'firmware/.pio/build/amoled175'
part=(build/'partitions.bin').read_bytes()
assert backup[0x8000:0x8000+len(part)]==part,'Partition table changed; stop.'
app=build/'firmware.bin'
assert app.stat().st_size<0x7c0000
python=str(Path.home()/'.espressif/python_env/idf5.5_py3.12_env/bin/python')
base=[python,'-m','esptool','--chip','esp32s3','--port','/dev/cu.usbmodem1101','--baud','921600','--before','usb_reset']
probe=subprocess.run(base+['read_mac'],capture_output=True,text=True,check=True)
assert manifest['device_mac'] in probe.stdout,'Wrong USB device; stop.'
print('Verified recovery image, app partition, and USB device identity.',flush=True)
subprocess.run(base+['write_flash','--flash_mode','keep','--flash_freq','keep','--flash_size','keep','0x10000',str(app)],check=True)
print('App-only flash complete.',flush=True)
