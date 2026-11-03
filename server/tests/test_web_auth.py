import hashlib
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_wappai import app, auth
from app import admin, wappai, config

ORIGIN={'Origin':'http://testserver'}
def login(c):
    code=admin.new_code(pair=True)
    r=c.post('/v1/web/login',headers=ORIGIN,json={'code':code})
    assert r.status_code==200
    return r,code

def test_browser_cookie_login_csrf_logout():
    c=TestClient(app);r,code=login(c)
    cookie=r.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'token' not in r.json()
    assert c.get('/v1/snapshot').status_code==200
    assert c.post('/v1/web/login',headers=ORIGIN,json={'code':code}).status_code==401
    for headers in ({},{'Origin':'null'},{'Origin':'https://evil.test'},{'Origin':'http://testserver.evil.test'}):
        assert c.post('/v1/settings',headers=headers,json={'live_transcription':True}).status_code==403
        assert c.post('/v1/web/logout',headers=headers,json={}).status_code==403
    assert c.post('/v1/settings',headers=ORIGIN,json={'live_transcription':False}).status_code==200
    token=c.cookies['wappai_web']
    assert c.post('/v1/web/logout',headers=ORIGIN,json={}).status_code==200
    assert not wappai.store.authorized(token)
    assert c.get('/v1/snapshot').status_code==401

def test_cookie_websocket_requires_origin():
    c=TestClient(app);login(c)
    for headers in ({},{'Origin':'https://evil.test'}):
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/v1/events',headers=headers):pass
    wappai.store.event({'type':'qa'})
    with c.websocket_connect('/v1/events',headers=ORIGIN) as ws:
        # A stored event makes this assertion deterministic without heartbeat waits.
        assert isinstance(ws.receive_json(),dict)

def test_native_authorization_unchanged():
    c=TestClient(app)
    assert c.get('/v1/snapshot',headers={'Authorization':'Bearer '+config.DEVICE_TOKEN}).status_code==401
    assert c.post('/v1/settings',headers=auth(),json={'live_transcription':False}).status_code==200
    assert c.post('/v1/web/login',json={'code':admin.new_code(pair=True)}).status_code==403

def test_https_cookie_secure():
    c=TestClient(app,base_url='https://testserver')
    r=c.post('/v1/web/login',headers={'Origin':'https://testserver'},json={'code':admin.new_code(pair=True)})
    assert r.status_code==200 and 'Secure' in r.headers['set-cookie']
