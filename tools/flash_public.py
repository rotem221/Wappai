"""Verified public release flash. A full flash backup precedes every write."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--board',choices=['1.75C'],required=True);p.add_argument('--backup',type=Path);p.add_argument('--dry-run',action='store_true');args=p.parse_args()
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
parts=manifest['parts'];commands=[]
for part in parts:
 file=root/part['file']
 if hashlib.sha256(file.read_bytes()).hexdigest()!=part['sha256']:raise SystemExit('Hash mismatch: '+part['file'])
backup=args.backup or Path.cwd()/('wappai-private-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.bin')
if backup.exists():raise SystemExit('Backup destination already exists; choose a new file.')
base=[sys.executable,'-m','esptool','--chip','esp32s3','--port',args.port,'--baud','460800']
commands.append(base+['read_flash','0','ALL',str(backup)])
write=base+['write_flash','--flash_size','16MB']
for part in parts:write.extend([part['offset'],str(root/part['file'])])
commands.append(write)
if args.dry_run:
 print(json.dumps({'board':'Waveshare 1.75C','backup_before_write':True,'commands':commands},indent=2));raise SystemExit(0)
print('This release is only for Waveshare ESP32-S3-Touch-AMOLED-1.75C (silver enclosure).')
print('Saving a private full-device backup before writing. Keep it private; it may contain credentials.')
for command in commands:subprocess.run(command,check=True)
print('Flash verified by esptool. Configure your Hub with configure_hub.py and pair Wi-Fi in the iOS app.')
