"""Explicit Hebrew address preferences; never infer gender from a name or voice."""
import json
import re
from .. import admin, config

QUESTION = "מה לשון הפנייה המועדפת: זכר, נקבה, או ניסוח ניטרלי?"
CHOICES = {"זכר": "masculine", "נקבה": "feminine", "ניטרלי": "neutral", "ניטרלית": "neutral"}


def remember(text, last_assistant=""):
    clean = text.strip().rstrip(".!? ")
    # A bare answer is meaningful only directly after our preference question.
    answer = re.fullmatch(r"(?:(?:אני )?(?:מעדיף|מעדיפה) )?(?:בלשון |לשון |בניסוח |ניסוח )?(זכר|נקבה|ניטרלי|ניטרלית)(?: בבקשה| תודה)?", clean)
    explicit = re.fullmatch(r"(?:פנה|פני|תפנה|תפני|דבר|דברי|תדבר|תדברי) (?:אליי|אלי|איתי) (?:ב)?(?:לשון |ניסוח )?(זכר|נקבה|ניטרלי|ניטרלית)(?: בבקשה)?", clean)
    match = explicit or (answer if QUESTION in last_assistant else None)
    if not match:
        return False
    value = CHOICES[match.group(1)]
    saved = admin.settings(); saved['user_address'] = value
    admin.SETTINGS_FILE.write_text(json.dumps(saved, ensure_ascii=False))
    config.USER_ADDRESS = value
    return True
