"""Small, meaning-preserving corrections before both captioning and speech.

This is not a general Hebrew grammar engine. Only unquoted question
introductions and affirmative remembering statements are normalized. Objects,
user address, negation and quotations are left intact.
"""
import re

_QUOTED = re.compile(r'("[^"\n]*"|״[^״\n]*״|“[^”\n]*”)')
_QUESTION = re.compile(
    r'(?P<prefix>^|(?<=[.!?])\s+)(?P<lead>(?:(?:ו?עכשיו|אז|לכן)\s+)?)'
    r'אני שואל(?:ת)?(?: אותך)?(?P<end>\s*:\s*|\s+(?=אם\b|האם\b))'
)
_REMEMBER = re.compile(r'(^|(?<=[.!?])\s+)((?:(?:ו?עכשיו|אז|לכן)\s+)?)אני זוכר(?:ת)?(?=\s|[.!?,:]|$)')


def self_reference(text: str, gender: str) -> str:
    if gender not in ('neutral', 'masculine', 'feminine'):
        return text

    def replace(match):
        stem = {'neutral': 'השאלה שלי היא', 'masculine': 'אני שואל', 'feminine': 'אני שואלת'}[gender]
        return match['prefix'] + match['lead'] + stem + match['end']

    parts = _QUOTED.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _QUESTION.sub(replace, parts[i])
        if gender == 'neutral':
            # Both forms express the completed act of remembering the same fact;
            # no claim of permanent storage is added.
            parts[i] = _REMEMBER.sub(r'\1\2זכרתי', parts[i])
    return ''.join(parts)
