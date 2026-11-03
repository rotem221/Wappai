"""ElevenLabs TTS and account discovery. Credentials remain on the Hub."""
import json
from typing import AsyncIterator
from urllib.parse import quote
import httpx
from .. import config

SECRET_FILE = config.DATA_DIR / 'elevenlabs.json'
BASE = 'https://api.elevenlabs.io'

def key() -> str:
    try:
        return json.loads(SECRET_FILE.read_text()).get('api_key', '') or config.ELEVENLABS_API_KEY
    except (OSError, ValueError):
        return config.ELEVENLABS_API_KEY

def save_key(value: str):
    import os
    temp = SECRET_FILE.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out: json.dump({'api_key': value}, out)
    temp.chmod(0o600);temp.replace(SECRET_FILE)

async def get(path: str, *, api_key: str | None = None, params=None):
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8)) as client:
        response = await client.get(BASE + path, headers={'xi-api-key': api_key or key()}, params=params)
        response.raise_for_status()
        return response.json()

async def voices(search='', cursor='', api_key=None):
    params = {'page_size': 50, 'include_total_count': False}
    if search: params['search'] = search
    if cursor: params['next_page_token'] = cursor
    data = await get('/v2/voices', api_key=api_key, params=params)
    return {'voices': [{'id': v['voice_id'], 'name': v.get('name', 'Voice'),
                       'description': v.get('description') or '', 'language': (v.get('labels') or {}).get('language', '')}
                      for v in data.get('voices', [])],
            'next_cursor': data.get('next_page_token') if data.get('has_more') else None}

async def models(api_key=None):
    data = await get('/v1/models', api_key=api_key)
    return [{'id': m['model_id'], 'name': m.get('name', m['model_id'])} for m in data
            if m.get('can_do_text_to_speech') and any(l.get('language_id') == 'he' for l in m.get('languages', []))]

def speech_body(text, emotion=None, model=None, style=None):
    model = model or config.ELEVENLABS_MODEL
    lively = (style or config.TTS_STYLE) == 'lively'
    positive = emotion in (None, '', 'speaking', 'idle', 'happy', 'joy', 'success', 'excited', 'proud', 'love')
    # v3 supports audio tags; use expressive delivery only for suitable emotions.
    if model.startswith('eleven_v3') and lively and positive:
        text = '[excited] ' + text
    settings = {'stability': 0.5, 'similarity_boost': 0.75}
    if not model.startswith(('eleven_v3', 'eleven_v4')):
        settings.update(style=0.35 if lively and positive else 0.1, speed=1.04 if lively and positive else 1.0)
    return {'text': text, 'model_id': model, 'voice_settings': settings}

async def stream(text: str, emotion=None, *, voice_id=None, model=None, style=None) -> AsyncIterator[bytes]:
    voice = voice_id or config.ELEVENLABS_VOICE_ID
    if not key() or not voice:
        raise RuntimeError('ElevenLabs is not connected or a voice is not selected')
    url = BASE + '/v1/text-to-speech/' + quote(voice, safe='') + '/stream'
    pending = b''; total = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
        async with client.stream('POST', url, params={'output_format': 'pcm_16000'},
                headers={'xi-api-key': key()}, json=speech_body(text, emotion, model, style)) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(4096):
                chunk = pending + chunk; end = len(chunk) // 2 * 2
                if end:
                    total += end
                    yield chunk[:end]
                pending = chunk[end:]
    if pending or not total:
        raise RuntimeError('Incomplete ElevenLabs audio')
