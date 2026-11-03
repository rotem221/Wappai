"""Durable, opt-in APNs outbox for one-owner Hubs. No transcript in push payloads."""
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from . import config


class Notifications:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        Path(path).chmod(0o600)  # Set before WAL creation so sidecars inherit private permissions.
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token TEXT, environment TEXT, timers INTEGER, meetings INTEGER, updated REAL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, device TEXT, body TEXT, attempts INTEGER DEFAULT 0, due REAL, expires REAL, state TEXT DEFAULT 'pending');''')
        self.db.commit()
        for suffix in ("-wal","-shm"):
            sidecar=Path(str(path)+suffix)
            if sidecar.exists():sidecar.chmod(0o600)

    def configured(self):
        return all(os.getenv(k) for k in ('APNS_KEY_ID', 'APNS_TEAM_ID', 'APNS_KEY_FILE', 'APNS_TOPIC')) and Path(os.getenv('APNS_KEY_FILE', '')).is_file()

    def register(self, installation, token, environment, timers, meetings):
        if not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', installation) or not re.fullmatch(r'[a-fA-F0-9]{32,256}', token):
            raise ValueError('Invalid installation or APNs token')
        if environment not in ('sandbox', 'production') or type(timers) is not bool or type(meetings) is not bool:
            raise ValueError('Invalid notification preferences')
        self.db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET token=excluded.token,environment=excluded.environment,timers=excluded.timers,meetings=excluded.meetings,updated=excluded.updated', (installation, token.lower(), environment, timers, meetings, time.time()))
        self.db.commit()

    def enqueue(self, kind, event_id, reference=''):
        if kind not in ('timers', 'meetings'): raise ValueError('Unknown notification kind')
        title, body = ('הטיימר הסתיים', 'הטיימר של Wappai הגיע לסיומו.') if kind == 'timers' else ('סיכום הפגישה מוכן', 'התמלול והסיכום זמינים בפגישות שלך.')
        payload = {'aps': {'alert': {'title': title, 'body': body}, 'sound': 'default', 'thread-id': 'wappai-'+kind}, 'kind': kind, 'reference': reference[:80]}
        now = time.time()
        for device in self.db.execute('SELECT * FROM devices WHERE '+kind+'=1'):
            ident = hashlib.sha256((kind+':'+event_id+':'+device['id']).encode()).hexdigest()
            self.db.execute('INSERT OR IGNORE INTO outbox(id,device,body,due,expires) VALUES (?,?,?,?,?)', (ident, device['id'], json.dumps(payload, ensure_ascii=False), now, now+(3600 if kind=='timers' else 86400)))
        self.db.commit()

    async def send(self, row, device):
        import jwt
        import httpx
        token = jwt.encode({'iss': os.environ['APNS_TEAM_ID'], 'iat': int(time.time())}, Path(os.environ['APNS_KEY_FILE']).read_text(), algorithm='ES256', headers={'kid': os.environ['APNS_KEY_ID']})
        host = 'api.sandbox.push.apple.com' if device['environment']=='sandbox' else 'api.push.apple.com'
        async with httpx.AsyncClient(http2=True, timeout=15) as client:
            r = await client.post(f'https://{host}/3/device/{device["token"]}', content=row['body'].encode(), headers={'authorization': 'bearer '+token, 'apns-topic': os.environ['APNS_TOPIC'], 'apns-push-type': 'alert', 'apns-priority': '10', 'apns-expiration': str(int(row['expires'])), 'apns-collapse-id': row['id']})
        return r.status_code, (r.json().get('reason', '') if r.content else '')

    async def drain(self):
        now = time.time()
        self.db.execute("UPDATE outbox SET state='expired' WHERE state='pending' AND expires<?", (now,))
        # Tokens are personal data: expire stale registrations and old delivery metadata.
        self.db.execute('DELETE FROM devices WHERE updated<?', (now-90*86400,))
        self.db.execute('DELETE FROM outbox WHERE expires<?', (now-7*86400,))
        self.db.commit()
        if not self.configured(): return
        for row in list(self.db.execute("SELECT * FROM outbox WHERE state='pending' AND due<=? LIMIT 20", (now,))):
            device = self.db.execute('SELECT * FROM devices WHERE id=?', (row['device'],)).fetchone()
            kind = json.loads(row['body'])['kind']
            if not device or not device[kind]:
                self.db.execute("UPDATE outbox SET state='cancelled' WHERE id=?", (row['id'],)); self.db.commit(); continue
            try: status, reason = await self.send(row, device)
            except Exception: status, reason = 503, 'TransportError'
            if status==200: state='sent'
            elif status==410 or reason in ('BadDeviceToken','DeviceTokenNotForTopic'):
                self.db.execute('DELETE FROM devices WHERE id=?', (device['id'],)); state='invalid_token'
            elif status in (400, 413): state='rejected'
            else: state='pending'
            self.db.execute('UPDATE outbox SET state=?,attempts=attempts+1,due=? WHERE id=?', (state, now+min(3600, 30*2**min(row['attempts'],7)), row['id']))
            self.db.commit()

    async def worker(self):
        while True:
            try:await self.drain()
            except Exception:
                import logging
                logging.getLogger('notifications').exception('Notification worker will retry')
            await asyncio.sleep(10)

    def routes(self, app, require):
        @app.get('/v1/notifications')
        async def status(request: Request):
            require(request)
            return {'configured': self.configured(), 'pending': self.db.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0]}

        @app.post('/v1/notifications/register')
        async def register(request: Request):
            require(request); d=await request.json()
            try: self.register(d.get('installation',''),d.get('token',''),d.get('environment',''),d.get('timers',True),d.get('meetings',True))
            except (ValueError, TypeError) as e: raise HTTPException(422,str(e))
            return {'configured':self.configured()}

        @app.post('/v1/notifications/unregister')
        async def unregister(request: Request):
            require(request); d=await request.json()
            self.db.execute('DELETE FROM devices WHERE id=?',(str(d.get('installation','')),)); self.db.commit()
            return {'ok':True}

service=Notifications(config.DATA_DIR/'notifications.sqlite3')
