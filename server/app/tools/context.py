"""Small live context injected into every question: local time, weather (Open-Meteo, no key), calendar, battery."""
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .. import config
from . import battery, calendar

_weather = {"t": 0, "text": ""}
DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
WMO = {0: "בהיר", 1: "בהיר ברובו", 2: "מעונן חלקית", 3: "מעונן", 45: "ערפל", 48: "ערפל", 51: "טפטוף", 53: "טפטוף",
       55: "טפטוף", 61: "גשם קל", 63: "גשם", 65: "גשם חזק", 71: "שלג", 80: "ממטרים", 81: "ממטרים", 82: "ממטרים חזקים",
       95: "סופת רעמים", 96: "סופת רעמים", 99: "סופת רעמים"}


_bg: set = set()


def invalidate_weather():
    _weather.update(t=0, text="")


def _refresh_later(coro):
    t = asyncio.get_running_loop().create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def weather() -> str:
    """Never makes a question wait: a stale value is returned at once and refreshed in the background."""
    if _weather["text"]:
        if time.time() - _weather["t"] > 15 * 60 and not _weather.get("busy"):
            _weather["busy"] = True
            _refresh_later(_fetch_weather())
        return _weather["text"]
    try:
        return await asyncio.wait_for(_fetch_weather(), 2.5)   # first time only
    except asyncio.TimeoutError:
        return ""


def _icon(code: int) -> str:
    """WMO code -> icon the board draws: sun, partly, cloud, fog, rain, snow, storm."""
    if code in (0, 1): return "sun"
    if code == 2: return "partly"
    if code == 3: return "cloud"
    if code in (45, 48): return "fog"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if code >= 95: return "storm"
    return "rain" if code >= 51 else "cloud"


def weather_data() -> dict:
    return _weather.get("data") or {}


MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]


def date_he(now: datetime | None = None) -> str:
    now = now or datetime.now(ZoneInfo(config.TZ))
    return f"יום {DAYS[now.weekday()]}, {now.day} ב{MONTHS[now.month - 1]}"


async def _fetch_weather() -> str:
    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={config.LAT}&longitude={config.LON}&current=temperature_2m,apparent_temperature,weather_code,"
               "wind_speed_10m,relative_humidity_2m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
               f"weather_code&forecast_days=2&timezone={config.TZ}")
        async with httpx.AsyncClient(timeout=6) as c:
            d = (await c.get(url)).json()
        cur, day = d["current"], d["daily"]
        txt = (f"מזג אוויר ב{config.CITY}: עכשיו {cur['temperature_2m']:.0f} מעלות "
               f"(מורגש כמו {cur['apparent_temperature']:.0f}), {WMO.get(cur['weather_code'], '')}, לחות {cur['relative_humidity_2m']}%, "
               f"רוח {cur['wind_speed_10m']:.0f} קמ\"ש. "
               f"היום: מינימום {day['temperature_2m_min'][0]:.0f}, מקסימום {day['temperature_2m_max'][0]:.0f} מעלות, "
               f"סיכוי לגשם {day['precipitation_probability_max'][0]}%. "
               f"מחר: {WMO.get(day['weather_code'][1], '')}, מינימום {day['temperature_2m_min'][1]:.0f}, "
               f"מקסימום {day['temperature_2m_max'][1]:.0f} מעלות, סיכוי לגשם {day['precipitation_probability_max'][1]}%.")
        icon = _icon(cur["weather_code"])
        data = {"city": config.CITY, "t": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
                "text": WMO.get(cur["weather_code"], ""), "icon": icon, "hum": cur["relative_humidity_2m"],
                "min": round(day["temperature_2m_min"][0]), "max": round(day["temperature_2m_max"][0]),
                "rain": day["precipitation_probability_max"][0],
                "tmin": round(day["temperature_2m_min"][1]), "tmax": round(day["temperature_2m_max"][1]),
                "ttext": WMO.get(day["weather_code"][1], ""), "ticon": _icon(day["weather_code"][1]),
                "train": day["precipitation_probability_max"][1]}
        _weather.update(t=time.time(), text=txt, data=data)
    except Exception:
        pass
    finally:
        _weather["busy"] = False
    return _weather["text"]


CAL_WORDS = ("יומן", "לוז", "לו\"ז", "פגיש", "אירוע", "שבוע", "מתי", "תכנון", "מתוכנן", "פנוי", "עסוק") + tuple(f"יום {d}" for d in DAYS)


async def build(device: dict | None = None, question: str = "") -> str:
    now = datetime.now(ZoneInfo(config.TZ))
    parts = [f"עכשיו יום {DAYS[now.weekday()]}, {now:%d/%m/%Y}, השעה {now:%H:%M}"]
    from ..display_intent import weather_requested
    wants_calendar = any(k in question for k in CAL_WORDS)
    async def cached_weather():
        # Unrelated questions must not wait for a cold weather network request.
        if not _weather.get('busy') and time.time()-_weather['t'] > 15*60:
            _weather['busy'] = True
            _refresh_later(_fetch_weather())
        return _weather['text']
    async def no_calendar(): return ''
    w, cal = await asyncio.gather(weather() if weather_requested(question) else cached_weather(),
                                  _safe(calendar.summary()) if wants_calendar else no_calendar())
    if w:
        parts.append(w)
    from . import composio
    g_active = composio._state().get("active", []) if composio.key() else []
    if "googlecalendar" in g_active:
        parts.append("ליומן Google ול-Gmail יש לך כלים (composio)" if "gmail" in g_active else "ליומן Google יש לך כלים (composio)")
    elif "gmail" in g_active:
        parts.append("ל-Gmail יש לך כלים (composio)")
    if not calendar.configured() and "googlecalendar" not in g_active:
        parts.append("היומן עדיין לא מחובר (מחברים בפאנל הניהול, לשונית חיבורים)")
    elif cal:
        parts.append(cal)
        if any(k in question for k in CAL_WORDS):
            wk = await _safe(calendar.week())
            if wk:
                parts.append("השבוע ביומן: " + wk)
    b = battery.summary((device or {}).get("battery"))
    if b:
        parts.append(b)
    return ". ".join(parts)


async def _safe(coro, timeout: float = 3.0) -> str:
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception:            # includes the timeout: an answer without the calendar beats a late answer
        return ""
