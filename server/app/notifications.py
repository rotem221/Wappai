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
        self._tokens = {}
        self._clients = {}
        self.db = sqlite3.connect(path, check_same_thread=False)
        Path(path).chmod(0o600)  # Set before WAL creation so sidecars inherit private permissions.
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, token TEXT, environment TEXT, timers INTEGER, meetings INTEGER, updated REAL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, device TEXT, body TEXT, attempts INTEGER DEFAULT 0, due REAL, expires REAL, state TEXT DEFAULT 'pending');''')
        if 'pips' not in {r[1] for r in self.db.execute('PRAGMA table_info(devices)')}:
            self.db.execute('ALTER TABLE devices ADD COLUMN pips INTEGER NOT NULL DEFAULT 0')
        self.db.commit()
        for suffix in ("-wal","-shm"):
            sidecar=Path(str(path)+suffix)
            if sidecar.exists():sidecar.chmod(0o600)

    def credentials(self, environment):
        if environment not in ('sandbox', 'production'):
            raise ValueError('Invalid APNs environment')
        prefix = 'APNS_' + environment.upper()
        # New Apple keys are environment-specific. Never mix a partial scoped
        # configuration with a legacy key for another environment.
        scoped = any(os.getenv(prefix + suffix) for suffix in ('_KEY_ID', '_KEY_FILE'))
        key_id = os.getenv(prefix + '_KEY_ID' if scoped else 'APNS_KEY_ID', '')
        key_file = os.getenv(prefix + '_KEY_FILE' if scoped else 'APNS_KEY_FILE', '')
        team, topic = os.getenv('APNS_TEAM_ID', ''), os.getenv('APNS_TOPIC', '')
        if not all((key_id, key_file, team, topic)) or not Path(key_file).is_file():
            return None
        return key_id, Path(key_file), team, topic

    def configured(self, environment=None):
        return any(self.credentials(e) is not None for e in
                   ((environment,) if environment else ('sandbox', 'production')))

    async def close(self):
        for _, client in self._clients.values():
            await client.aclose()
        self._clients.clear()
        self._tokens.clear()

    def register(self, installation, token, environment, timers, meetings, pips=False):
        if not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', installation) or not re.fullmatch(r'[a-fA-F0-9]{32,256}', token):
            raise ValueError('Invalid installation or APNs token')
        if environment not in ('sandbox', 'production') or type(timers) is not bool or type(meetings) is not bool or type(pips) is not bool:
            raise ValueError('Invalid notification preferences')
        self.db.execute('INSERT INTO devices(id,token,environment,timers,meetings,updated,pips) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET token=excluded.token,environment=excluded.environment,timers=excluded.timers,meetings=excluded.meetings,updated=excluded.updated,pips=excluded.pips', (installation, token.lower(), environment, timers, meetings, time.time(), pips))
        self.db.commit()

    def enqueue(self, kind, event_id, reference='', stage=''):
        if kind not in ('timers', 'meetings', 'pips'): raise ValueError('Unknown notification kind')
        title, body = ('הטיימר הסתיים', 'הטיימר של Wappai הגיע לסיומו.') if kind == 'timers' else ('סיכום הפגישה מוכן', 'התמלול והסיכום זמינים בפגישות שלך.')
        if kind=='pips':
            title,body=('התצוגה המקדימה מוכנה','אפשר לפתוח את הגלריה ולאשר את עיצוב ה־Pip.') if stage=='preview_ready' else ('ה־Pip החדש מוכן','הדמות והאנימציות שלה מוכנות בגלריה.')
        payload = {'aps': {'alert': {'title': title, 'body': body}, 'sound': 'default', 'thread-id': 'wappai-'+kind}, 'kind': kind, 'reference': reference[:80]}
        now = time.time()
        for device in self.db.execute('SELECT * FROM devices WHERE '+kind+'=1'):
            ident = hashlib.sha256((kind+':'+event_id+':'+device['id']).encode()).hexdigest()
            self.db.execute('INSERT OR IGNORE INTO outbox(id,device,body,due,expires) VALUES (?,?,?,?,?)', (ident, device['id'], json.dumps(payload, ensure_ascii=False), now, now+(3600 if kind=='timers' else 86400)))
        self.db.commit()

    async def send(self, row, device):
        import jwt
        import httpx
        environment = device['environment']
        credentials = self.credentials(environment)
        if credentials is None:
            return 503, 'EnvironmentNotConfigured'
        key_id, key_file, team, topic = credentials
        stat = key_file.stat()
        identity = (key_id, str(key_file), stat.st_mtime_ns, stat.st_size, team, topic)
        now = int(time.time())
        cached = self._tokens.get(environment)
        if cached is None or cached[0] != identity or not 0 <= now-cached[1] < 50*60:
            token = jwt.encode({'iss': team, 'iat': now}, key_file.read_text(), algorithm='ES256', headers={'kid': key_id})
            self._tokens[environment] = (identity, now, token)
        else:
            token = cached[2]
        connection = self._clients.get(environment)
        if connection is None or connection[0] != identity:
            if connection is not None:
                await connection[1].aclose()
            client = httpx.AsyncClient(http2=True, timeout=15)
            self._clients[environment] = (identity, client)
        else:
            client = connection[1]
        host = 'api.sandbox.push.apple.com' if environment=='sandbox' else 'api.push.apple.com'
        r = await client.post(f'https://{host}/3/device/{device["token"]}', content=row['body'].encode(), headers={'authorization': 'bearer '+token, 'apns-topic': topic, 'apns-push-type': 'alert', 'apns-priority': '10', 'apns-expiration': str(int(row['expires'])), 'apns-collapse-id': row['id']})
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
        try:
            while True:
                try:await self.drain()
                except Exception:
                    import logging
                    logging.getLogger('notifications').exception('Notification worker will retry')
                await asyncio.sleep(10)
        finally:
            await self.close()

    def routes(self, app, require):
        @app.get('/v1/notifications')
        async def status(request: Request):
            require(request)
            return {'configured': self.configured(), 'environments': {e: self.configured(e) for e in ('sandbox', 'production')}, 'pending': self.db.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0]}

        @app.post('/v1/notifications/register')
        async def register(request: Request):
            require(request); d=await request.json()
            try: self.register(d.get('installation',''),d.get('token',''),d.get('environment',''),d.get('timers',True),d.get('meetings',True),d.get('pips',False))
            except (ValueError, TypeError) as e: raise HTTPException(422,str(e))
            return {'configured':self.configured(d['environment'])}

        @app.post('/v1/notifications/unregister')
        async def unregister(request: Request):
            require(request); d=await request.json()
            self.db.execute('DELETE FROM devices WHERE id=?',(str(d.get('installation','')),)); self.db.commit()
            return {'ok':True}

service=Notifications(config.DATA_DIR/'notifications.sqlite3')
