"""Read-only calendar from one or more secret iCal (ICS) addresses — no OAuth, no Google project.

Google Calendar: Settings -> (your calendar) -> Integrate calendar -> "Secret address in iCal format".
The addresses live in CLAUDE_WORKDIR/calendar_urls.txt (one per line, chmod 600) or CALENDAR_ICS (space separated).
Events of today (from now) and tomorrow are added to the context of every question; the rest of the week on demand.
"""
import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .. import config

log = logging.getLogger("calendar")
URLS_FILE = Path(config.CLAUDE_WORKDIR) / "calendar_urls.txt"
CACHE_S = 10 * 60
_cache = {"t": 0.0, "events": []}
_lock = asyncio.Lock()

try:
    import icalendar
    import recurring_ical_events
    AVAILABLE = True
except ImportError:                      # optional dependency
    AVAILABLE = False


def urls() -> list[str]:
    out = config.env("CALENDAR_ICS", "").split()
    try:
        out += [l.strip() for l in URLS_FILE.read_text().splitlines() if l.strip().startswith("http")]
    except OSError:
        pass
    return out


def configured() -> bool:
    return AVAILABLE and bool(urls())


def _parse(ics: bytes, start: datetime, end: datetime, tz: ZoneInfo) -> list[dict]:
    cal = icalendar.Calendar.from_ical(ics)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s = ev.decoded("DTSTART")
        e = ev.decoded("DTEND") if ev.get("DTEND") else None
        all_day = isinstance(s, date) and not isinstance(s, datetime)
        if all_day:
            s_dt = datetime.combine(s, datetime.min.time(), tz)
            e_dt = datetime.combine(e, datetime.min.time(), tz) if e else s_dt + timedelta(days=1)
        else:
            s_dt = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
            e_dt = (e.astimezone(tz) if e.tzinfo else e.replace(tzinfo=tz)) if isinstance(e, datetime) else s_dt
        out.append({"start": s_dt, "end": e_dt, "all_day": all_day, "title": str(ev.get("SUMMARY", "")).strip() or "(ללא כותרת)",
                    "where": str(ev.get("LOCATION", "")).strip()})
    return out


_bg: set = set()


async def events() -> list[dict]:
    """Events from the start of today until 7 days ahead, sorted. Cached for 10 minutes; a stale cache is returned
    at once and refreshed in the background, so a question never waits for the calendar server."""
    if not configured():
        return []
    if _cache["t"] and time.time() - _cache["t"] >= CACHE_S and not _lock.locked():
        t = asyncio.get_running_loop().create_task(_fetch())
        _bg.add(t)
        t.add_done_callback(_bg.discard)
        return _cache["events"]
    return await _fetch()


async def _fetch() -> list[dict]:
    async with _lock:
        if time.time() - _cache["t"] < CACHE_S:
            return _cache["events"]
        tz = ZoneInfo(config.TZ)
        start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=8)
        evs: list[dict] = []
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            for u in urls():
                try:
                    r = await c.get(u)
                    r.raise_for_status()
                    evs += await asyncio.to_thread(_parse, r.content, start, end, tz)
                except Exception as e:                   # never log the secret address itself
                    log.warning("calendar fetch failed (%s): %s", u.split("/")[2] if "//" in u else "?", type(e).__name__)
        evs.sort(key=lambda x: (x["start"], not x["all_day"]))
        _cache.update(t=time.time(), events=evs)
        return evs


def _fmt(ev: dict) -> str:
    t = "כל היום" if ev["all_day"] else f"{ev['start']:%H:%M}" + (f"-{ev['end']:%H:%M}" if ev["end"] > ev["start"] else "")
    return f"{t} {ev['title']}" + (f" ({ev['where']})" if ev["where"] else "")


DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


async def summary() -> str:
    """Short context line: the rest of today and tomorrow; if both are empty, the next event this week."""
    if not configured():
        return ""
    evs = await events()
    tz = ZoneInfo(config.TZ)
    now = datetime.now(tz)
    today, tomorrow = now.date(), now.date() + timedelta(days=1)
    rest = [e for e in evs if e["start"].date() == today and (e["all_day"] or e["end"] >= now)]
    tmr = [e for e in evs if e["start"].date() == tomorrow]
    parts = []
    parts.append("ביומן היום: " + ("; ".join(_fmt(e) for e in rest[:8]) if rest else "אין עוד אירועים"))
    parts.append("מחר: " + ("; ".join(_fmt(e) for e in tmr[:8]) if tmr else "אין אירועים"))
    if not rest and not tmr:
        nxt = next((e for e in evs if e["start"] > now), None)
        if nxt:
            parts.append(f"האירוע הבא: יום {DAYS[nxt['start'].weekday()]} {nxt['start']:%d/%m} {_fmt(nxt)}")
    return ". ".join(parts)


async def week() -> str:
    evs = await events()
    if not evs:
        return "אין אירועים ביומן בשבוע הקרוב" if configured() else "היומן לא מחובר"
    now = datetime.now(ZoneInfo(config.TZ))
    by_day: dict = {}
    for e in evs:
        if e["end"] < now and not e["all_day"]:
            continue
        by_day.setdefault(e["start"].date(), []).append(_fmt(e))
    return " | ".join(f"יום {DAYS[d.weekday()]} {d:%d/%m}: " + "; ".join(v) for d, v in sorted(by_day.items()))
