"""Authenticated voice setup, discovery, selection and a short local-app preview."""
import asyncio, io, json, re, wave
from urllib.parse import quote
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response
from .. import admin, config
from . import elevenlabs, tts

_ID = re.compile(r'[A-Za-z0-9_-]{1,100}')
_preview_lock = asyncio.Lock()

def status():
    return {'provider': config.TTS_PROVIDER, 'style': config.TTS_STYLE,
            'edge_voice': config.TTS_VOICE, 'voice_id': config.ELEVENLABS_VOICE_ID,
            'model_id': config.ELEVENLABS_MODEL, 'connected': bool(elevenlabs.key()),
            'user_address': config.USER_ADDRESS, 'assistant_gender': config.ASSISTANT_GENDER}

async def upstream(operation):
    try:
        return await operation
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        detail = 'מפתח ElevenLabs אינו תקין או חסרות לו הרשאות לקולות ולדיבור' if code in (401, 403) else 'ElevenLabs אינו זמין כרגע או שמכסת החשבון הסתיימה'
        raise HTTPException(422 if code in (401,403,404) else 502, detail) from None
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(502, 'לא ניתן להתחבר ל־ElevenLabs כרגע') from None

def connected():
    if not elevenlabs.key(): raise HTTPException(409, 'יש לחבר חשבון ElevenLabs תחילה')

async def validate_voice(voice, model):
    connected()
    if not isinstance(voice,str) or not _ID.fullmatch(voice) or not isinstance(model,str) or not _ID.fullmatch(model):
        raise HTTPException(422, 'יש לבחור קול ומודל')
    available = await upstream(elevenlabs.models())
    if model not in {m['id'] for m in available}: raise HTTPException(422, 'המודל שנבחר אינו תומך בעברית')
    await upstream(elevenlabs.get('/v1/voices/' + quote(voice,safe='')))

def register(app, require):
    @app.post('/v1/voice/preferences')
    async def preferences(request:Request):
        require(request);body=await request.json()
        if not isinstance(body,dict) or not body or set(body)-{'user_address','assistant_gender'}:
            raise HTTPException(422,'העדפת דיבור לא תקינה')
        for k,v in body.items():
            if not isinstance(v,str) or not admin.EDITABLE[k][2](v):
                raise HTTPException(422,'העדפת דיבור לא תקינה')
        saved=admin.settings();saved.update(body)
        admin.SETTINGS_FILE.write_text(json.dumps(saved,ensure_ascii=False));admin.apply_settings()
        return status()

    @app.get('/v1/voice')
    async def current(request:Request):
        require(request);return status()

    @app.post('/v1/voice/connect')
    async def connect(request:Request):
        require(request);body=await request.json();key=body.get('api_key')
        if not isinstance(key,str) or not 16 <= len(key.strip()) <= 512 or any(c.isspace() for c in key.strip()):
            raise HTTPException(422,'מפתח API אינו תקין')
        key=key.strip()
        listing=await upstream(elevenlabs.voices(api_key=key))
        models=await upstream(elevenlabs.models(api_key=key))
        if not models:raise HTTPException(422,'בחשבון לא נמצא מודל דיבור התומך בעברית')
        elevenlabs.save_key(key)
        return {**status(),**listing,'models':models}

    @app.post('/v1/voice/search')
    async def search(request:Request):
        require(request);connected();body=await request.json()
        query=body.get('search','');cursor=body.get('cursor','')
        if not isinstance(query,str) or len(query)>100 or not isinstance(cursor,str) or len(cursor)>2000:raise HTTPException(422,'חיפוש לא תקין')
        listing=await upstream(elevenlabs.voices(query,cursor))
        return {**listing,'models':await upstream(elevenlabs.models())}

    @app.post('/v1/voice')
    async def select(request:Request):
        require(request);body=await request.json()
        provider=body.get('provider');style=body.get('style','lively')
        if provider not in ('edge','elevenlabs') or style not in ('lively','natural'):raise HTTPException(422,'בחירת קול לא תקינה')
        saved=admin.settings()
        if provider=='elevenlabs':
            voice=body.get('voice_id');model=body.get('model_id')
            await validate_voice(voice,model)
            saved.update(elevenlabs_voice_id=voice,elevenlabs_model=model)
        else:
            voice=body.get('edge_voice','he-IL-HilaNeural')
            if voice not in ('he-IL-HilaNeural','he-IL-AvriNeural'):raise HTTPException(422,'קול לא תקין')
            saved['tts_voice']=voice
        saved.update(tts_provider=provider,tts_style=style)
        admin.SETTINGS_FILE.write_text(json.dumps(saved,ensure_ascii=False));admin.apply_settings()
        return status()

    @app.post('/v1/voice/preview')
    async def preview(request:Request):
        require(request);body=await request.json()
        voice=body.get('voice_id');model=body.get('model_id');style=body.get('style','lively')
        if style not in ('lively','natural'):raise HTTPException(422,'סגנון לא תקין')
        await validate_voice(voice,model)
        if _preview_lock.locked():raise HTTPException(429,'דוגמת קול כבר בהכנה')
        async def generate():
            pcm=bytearray()
            async for chunk in elevenlabs.stream('שלום! איזה כיף לשמוע אותך. אני כאן כדי לעזור.', 'speaking',voice_id=voice,model=model,style=style):
                pcm.extend(chunk)
                if len(pcm)>32000*25:raise RuntimeError('Preview too long')
            out=io.BytesIO()
            with wave.open(out,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(pcm)
            return out.getvalue()
        async with _preview_lock:data=await upstream(generate())
        return Response(data,media_type='audio/wav',headers={'Cache-Control':'no-store'})
