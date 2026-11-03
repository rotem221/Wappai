"""Turns the model's streamed text into events: emotion / gesture / timer tags and speakable sentences."""
import re
from dataclasses import dataclass, field

TAG_EMO = re.compile(r"\[([a-z_]+)\]")
TAG_XML = re.compile(r"<(gesture|timer|timer_cancel|meeting_start|show)\b([^>]*)/?>")
ATTR = re.compile(r'(\w+)="([^"]*)"')
SENT_END = re.compile(r"[.!?…]+\s+|\n+")   # punctuation must be followed by a space: "claude.ai", "3.5" stay whole
CLAUSE = re.compile(r"[,;:]\s")      # the first sentence may be cut at a comma, so speech starts sooner
FIRST_CLAUSE_MIN = 18


@dataclass
class Event:
    kind: str                      # emotion | gesture | timer | timer_cancel | sentence
    value: str = ""
    attrs: dict = field(default_factory=dict)


class ReplyParser:
    def __init__(self, emotions: set[str]):
        self.emotions = emotions
        self.buf = ""
        self.spoke = False

    def feed(self, chunk: str) -> list[Event]:
        self.buf += chunk
        return self._drain(final=False)

    def finish(self) -> list[Event]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[Event]:
        out: list[Event] = []
        while True:
            head_limit = len(self.buf) if final else self._safe_len()
            head = self.buf[:head_limit]
            # first tag or sentence end in the safe part
            m_tag = None
            for rx in (TAG_EMO, TAG_XML):
                m = rx.search(head)
                if m and (m_tag is None or m.start() < m_tag.start()):
                    m_tag = m
            m_end = SENT_END.search(head)
            if not self.spoke:
                for m_c in CLAUSE.finditer(head):
                    if m_end and m_c.start() > m_end.start():
                        break
                    if len(head[:m_c.start()].strip()) >= FIRST_CLAUSE_MIN:
                        m_end = m_c
                        break
            if m_tag and (not m_end or m_tag.start() <= m_end.start()):
                self._text(out, head[:m_tag.start()], flush=True)
                if m_tag.re is TAG_EMO:
                    if m_tag.group(1) in self.emotions:
                        out.append(Event("emotion", m_tag.group(1)))
                else:
                    kind = m_tag.group(1)
                    out.append(Event(kind, attrs=dict(ATTR.findall(m_tag.group(2)))))
                self.buf = self.buf[m_tag.end():]
                continue
            if m_end:
                self._text(out, head[:m_end.end()], flush=True)
                self.spoke = self.spoke or any(e.kind == "sentence" for e in out)
                self.buf = self.buf[m_end.end():]
                continue
            if final:
                self._text(out, self.buf, flush=True)
                self.buf = ""
            return out

    def _safe_len(self):
        for i, ch in enumerate(self.buf):
            if ch == "<" and ">" not in self.buf[i:]:
                return i
            if ch == "[" and "]" not in self.buf[i:]:
                return i
        return len(self.buf)

    @staticmethod
    def _text(out, s, flush):
        s = re.sub(r"[*#_`>~]", "", s).strip()
        if s:
            out.append(Event("sentence", s))
