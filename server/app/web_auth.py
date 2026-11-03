"""Same-origin browser sessions; native clients keep their Bearer authorization."""
from urllib.parse import urlsplit
from fastapi import HTTPException
from . import admin, config

COOKIE = 'wappai_web'

def same_origin(request):
    origin = request.headers.get('origin', '')
    if not origin or origin == 'null': return False
    try: parsed = urlsplit(origin)
    except ValueError: return False
    if parsed.scheme not in ('http','https') or parsed.path or parsed.query or parsed.fragment: return False
    host = request.headers.get('host', '')
    # The reverse proxy preserves Host. Do not trust client-supplied forwarding headers.
    expected_scheme = 'https' if request.url.scheme in ('https','wss') else 'http'
    public = urlsplit(config.PUBLIC_URL)
    return parsed.netloc == host and (parsed.scheme == expected_scheme or (parsed.scheme=='https' and parsed.netloc==public.netloc))

def guard(request):
    if not same_origin(request): raise HTTPException(403,'Origin mismatch')

def authorized(request,store):
    token=request.cookies.get(COOKIE,'')
    sid=request.cookies.get(admin.COOKIE,'')
    return store.authorized(token) or bool(sid and admin._h256(sid) in admin._load()['sessions'])
