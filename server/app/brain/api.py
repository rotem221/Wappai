"""Optional brain: Anthropic Messages API (set BRAIN=api and ANTHROPIC_API_KEY). Keeps a short history."""
import json
import time
from typing import AsyncIterator

import httpx

from .. import config
from .persona import system_prompt


class AnthropicAPI:
    def __init__(self):
        self.history: list[dict] = []
        self.last = 0.0

    async def reset(self):
        self.history = []

    async def ask(self, text: str, context: str = "") -> AsyncIterator[str]:
        if time.time() - self.last > 20 * 60:
            self.history = []
        self.last = time.time()
        content = f"[הקשר: {context}]\n{text}" if context else text
        self.history.append({"role": "user", "content": content})
        self.history = self.history[-16:]
        body = {"model": config.API_MODEL, "max_tokens": 400, "system": system_prompt(),
                "messages": self.history, "stream": True}
        headers = {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        full = ""
        async with httpx.AsyncClient(timeout=60) as c:
            async with c.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=body) as r:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    ev = json.loads(line[5:])
                    if ev.get("type") == "content_block_delta" and ev["delta"].get("type") == "text_delta":
                        full += ev["delta"]["text"]
                        yield ev["delta"]["text"]
        self.history.append({"role": "assistant", "content": full or "..."})

    async def status(self) -> dict:
        return {"installed": bool(config.ANTHROPIC_API_KEY), "backend": "api"}
