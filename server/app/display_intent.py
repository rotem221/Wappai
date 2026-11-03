"""Conservative presentation hints. These never execute a home command."""
import re

def weather_requested(text: str) -> bool:
    text = text.lower()
    # Hebrew word boundaries matter: מזג is not a substring trigger for מזגן.
    explicit = re.search(r'מזג\s*(?:ה?אוויר|ה?אויר)|מז["״]א|תחזית|\bweather\b|\bforecast\b', text)
    if explicit:
        return True
    if home_requested(text):
        return False
    return bool(re.search(r'גשם|(?:חם|קר)\s+(?:היום|מחר)|(?:טמפרטורה|מעלות).*(?:בחוץ|היום|מחר)', text))

def home_requested(text: str) -> bool:
    return bool(re.search(r'מזג(?:ן|נים)|תריס|מנור|אורות|תאורה|מתג|מאוורר|\b(?:air\s*conditioner|thermostat|lights?|switch|fan|blinds)\b', text.lower()))

def requested_device(text: str, items: list[dict]) -> dict | None:
    """Match a unique labelled device, never guess between two rooms/entities."""
    def words(value):
        tokens = re.findall(r'[א-ת]+|[a-z]+', value.lower())
        return {re.sub(r'^[בהל](?=מזגן|חדר|סלון|מטבח|אור|תריס)', '', t) for t in tokens}
    query = words(text)
    query |= {t[1:] for t in list(query) if len(t)>3 and t[0] in 'בהלו'}
    climate = bool(re.search(r'מזגן|מזגנים|air\s*conditioner|thermostat', text.lower()))
    candidates = []
    for item in items:
        if item.get('kind') not in ('climate', 'light', 'switch', 'fan', 'cover', 'input_boolean'):
            continue
        if climate and item['kind'] != 'climate':
            continue
        name = words(item.get('name', ''))
        if len(name) >= 2 and name <= query:
            candidates.append(item)
    return candidates[0] if len(candidates) == 1 else None
