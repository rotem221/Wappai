"""Bounded local recording spool and optional private S3-compatible archive.
Credentials stay on the Hub. Files are removed only after verified upload and explicit cache eviction.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path
from . import config

PCM_BYTES_SECOND=32000

def capacity():
    root=config.DATA_DIR/'meetings';root.mkdir(parents=True,exist_ok=True)
    used=0
    for path in root.rglob('*'):
        try:
            if path.is_file():used+=path.stat().st_size
        except FileNotFoundError:pass  # An encoder atomically replaced a part while we counted.
    quota=int(os.getenv('MEETING_QUOTA_MB','4096'))*1024*1024
    reserve=int(os.getenv('MEETING_RESERVE_MB','256'))*1024*1024
    free=max(0,min(quota-used,shutil.disk_usage(root).free-reserve))
    # Reserve space for both an open WAV and encoded output, not optimistic AAC estimates.
    return {'used_bytes':used,'quota_bytes':quota,'available_bytes':free,'remaining_seconds':int(free/(PCM_BYTES_SECOND*2)), 'max_session_seconds':18000, 'cloud_configured':bool(os.getenv('MEETING_S3_BUCKET')), 'mode':'hub-and-cloud' if os.getenv('MEETING_S3_BUCKET') else 'hub-local', 'device_offline_seconds':98}

def client():
    import boto3
    from botocore.config import Config
    endpoint=os.getenv('MEETING_S3_ENDPOINT') or None
    if endpoint and not endpoint.startswith('https://'):raise ValueError('S3 endpoint must use HTTPS')
    return boto3.client('s3',endpoint_url=endpoint,region_name=os.getenv('AWS_DEFAULT_REGION','us-east-1'),config=Config(connect_timeout=10,read_timeout=60,retries={'max_attempts':3,'mode':'standard'}))

def archive(path:Path):
    bucket=os.getenv('MEETING_S3_BUCKET')
    if not bucket:return None
    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    key='meetings/'+path.parent.name+'/'+path.name
    s3=client()
    s3.upload_file(str(path),bucket,key,ExtraArgs={'Metadata':{'sha256':digest},'ContentType':'audio/mp4','ServerSideEncryption':'AES256'})
    head=s3.head_object(Bucket=bucket,Key=key)
    if head['ContentLength']!=path.stat().st_size or head.get('Metadata',{}).get('sha256')!=digest:raise IOError('Cloud verification failed')
    receipt={'key':key,'bucket':bucket,'sha256':digest,'bytes':path.stat().st_size}
    temp=path.with_suffix('.cloud.tmp'); temp.write_text(json.dumps(receipt));temp.replace(path.with_suffix('.cloud.json'))
    return receipt

def remote_audio(directory:Path):
    receipt=directory/'audio.cloud.json'
    if not receipt.is_file():return None
    item=json.loads(receipt.read_text())
    if item['bucket']!=os.getenv('MEETING_S3_BUCKET'):return None
    return client().generate_presigned_url('get_object',Params={'Bucket':item['bucket'],'Key':item['key']},ExpiresIn=120)

def evict(directory:Path):
    if os.getenv('MEETING_CLOUD_EVICT','0')!='1':return
    # Keep local audio until the complete final recording has been verified in the bucket.
    if not (directory/'audio.cloud.json').is_file():return
    for path in list(directory.glob('*.m4a')):
        if path.with_suffix('.cloud.json').is_file():path.unlink()

def delete_archive(directory:Path):
    receipts=list(directory.glob('*.cloud.json'))
    if not receipts:return
    s3=client()
    for path in receipts:
        item=json.loads(path.read_text())
        if item['bucket']!=os.getenv('MEETING_S3_BUCKET'):raise ValueError('Archive bucket changed; restore original configuration before deletion')
        s3.delete_object(Bucket=item['bucket'],Key=item['key'])

async def archive_worker():
    """Retry unfinished uploads after network failure or Hub restart; never auto-delete meetings."""
    import asyncio
    import logging
    while True:
        if os.getenv('MEETING_S3_BUCKET'):
            try:
                root=config.DATA_DIR/'meetings'
                pending=[p for p in root.glob('*/*.m4a') if '.encoding.' not in p.name and '.joining.' not in p.name and not p.with_suffix('.cloud.json').exists()]
                for path in sorted(pending)[:12]:
                    # _encode writes temporary output; final names are published only after successful encoding.
                    await asyncio.to_thread(archive,path)
                for meta in root.glob('*/meta.json'):
                    info=json.loads(meta.read_text())
                    if info.get('state') in ('done','transcribed','summary_unavailable'):
                        await asyncio.to_thread(evict,meta.parent)
            except Exception:logging.getLogger('meeting-storage').warning('Archive retry pending; local files retained')
        await asyncio.sleep(60)
