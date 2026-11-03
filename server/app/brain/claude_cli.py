"""Brain backed by the official Claude Code CLI, signed in with the owner's own subscription.

One long-lived `claude -p` process in streaming-JSON mode keeps the conversation (and avoids a
cold start per question). It is restarted after a long idle period or many turns so context
stays small and fast.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator

from .. import config
from .persona import system_prompt

log = logging.getLogger("brain.cli")

IDLE_RESET_S = 20 * 60
MAX_TURNS = 30
BLOCKED_TOOLS = "Bash Edit Write MultiEdit Read Glob Grep NotebookEdit Task TodoWrite KillShell BashOutput SlashCommand"


class ClaudeCLI:
    def __init__(self):
        self.proc: asyncio.subprocess.Process | None = None
        self.turns = 0
        self.last = 0.0
        self.lock = asyncio.Lock()
        self.last_ok = True       # False when the last turn ended in an error (not signed in, usage limit, ...)
        Path(config.CLAUDE_WORKDIR).mkdir(parents=True, exist_ok=True)

    def _args(self):
        a = [config.CLAUDE_BIN, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
             "--verbose", "--include-partial-messages", "--model", config.CLAUDE_MODEL,
             "--system-prompt", system_prompt(), "--disallowedTools", BLOCKED_TOOLS]
        allowed = ["WebSearch"]
        mcp = Path(config.CLAUDE_WORKDIR) / "mcp.json"
        if mcp.exists():
            a += ["--mcp-config", str(mcp), "--strict-mcp-config"]
            try:
                for name in json.loads(mcp.read_text())["mcpServers"]:
                    allowed.append(f"mcp__{name}")
            except Exception:
                pass
        a += ["--allowedTools", " ".join(allowed)]
        return a

    async def _ensure(self):
        stale = self.proc and (time.time() - self.last > IDLE_RESET_S or self.turns >= MAX_TURNS)
        if self.proc and (self.proc.returncode is not None or stale):
            await self.reset()
        if not self.proc:
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)        # use the subscription login, never an API key by accident
            self.proc = await asyncio.create_subprocess_exec(
                *self._args(), cwd=config.CLAUDE_WORKDIR, env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                limit=4 * 1024 * 1024)
            self.turns = 0
            asyncio.create_task(self._drain_stderr(self.proc))
            log.info("claude started (pid %s, model %s)", self.proc.pid, config.CLAUDE_MODEL)

    async def _drain_stderr(self, proc):
        while proc.stderr and (line := await proc.stderr.readline()):
            log.warning("claude: %s", line.decode(errors="replace").rstrip())

    async def reset(self):
        if self.proc:
            try:
                self.proc.kill()
                await self.proc.wait()
            except ProcessLookupError:
                pass
        self.proc = None

    async def ask(self, text: str, context: str = "") -> AsyncIterator[str]:
        """Streams the reply text. If the caller stops early (barge-in), the rest of the turn is drained in the
        background before the next question, so a cut-off answer never leaks into the next one."""
        await self.lock.acquire()
        done = False
        try:
            await self._ensure()
            self.last = time.time()
            self.turns += 1
            content = f"[הקשר: {context}]\n{text}" if context else text
            msg = {"type": "user", "message": {"role": "user", "content": content}}
            self.proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
            await self.proc.stdin.drain()
            got_delta = False
            held: list[str] = []          # whole-message text (no deltas): only spoken if the turn succeeded
            while True:
                try:
                    line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=90)
                except asyncio.TimeoutError:
                    done = True
                    await self.reset()
                    raise RuntimeError("claude did not answer in 90 s")
                if not line:
                    done = True
                    await self.reset()
                    raise RuntimeError("claude exited")
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = ev.get("type")
                if t == "stream_event":
                    e = ev.get("event", {})
                    if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                        got_delta = True
                        yield e["delta"]["text"]
                elif t == "assistant" and not got_delta:
                    for c in ev.get("message", {}).get("content", []):
                        if c.get("type") == "text":
                            held.append(c["text"])
                elif t == "result":
                    done = True
                    self.last = time.time()
                    if ev.get("is_error") or ev.get("subtype", "success") != "success":
                        msg = str(ev.get("result", ""))
                        log.error("claude result error: %s", msg)
                        self.last_ok = False
                        await self.reset()        # never carry failed turns (e.g. before sign-in) into the next conversation
                        if not got_delta:
                            if "login" in msg.lower() or "logged in" in msg.lower():
                                yield "[sad] אני עוד לא מחובר למוח של Claude. צריך להתחבר בשרת."
                            elif "limit" in msg.lower():
                                yield "[sleepy] הגעתי למגבלת השימוש כרגע. ננסה שוב קצת אחר כך."
                            else:
                                yield "[sad] משהו השתבש אצלי במוח. נסה שוב עוד רגע."
                        return
                    self.last_ok = True
                    for h in held:
                        yield h
                    return
        finally:
            if done or self.proc is None:
                self.lock.release()
            else:                         # interrupted mid-turn: finish reading it, then free the lock
                asyncio.get_running_loop().create_task(self._drain_turn())

    async def _drain_turn(self):
        """Ends an interrupted turn quickly: asks the CLI to stop (stream-json control request, as the Agent SDK's
        interrupt() does), then reads up to that turn's result. Falls back to restarting the CLI."""
        t0 = time.time()
        try:
            req = {"type": "control_request", "request_id": f"int_{int(t0 * 1000)}", "request": {"subtype": "interrupt"}}
            self.proc.stdin.write((json.dumps(req) + "\n").encode())
            await self.proc.stdin.drain()
            while True:
                left = 12 - (time.time() - t0)
                if left <= 0:
                    raise asyncio.TimeoutError
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                if not line:
                    await self.reset()
                    return
                try:
                    if json.loads(line).get("type") == "result":
                        self.last = time.time()
                        log.info("interrupted turn ended in %.1fs", time.time() - t0)
                        return
                except json.JSONDecodeError:
                    pass
        except Exception:
            log.warning("interrupt did not end the turn, restarting the CLI")
            await self.reset()
        finally:
            self.lock.release()

    async def status(self) -> dict:
        """Checks the CLI is installed and signed in (cheap: `claude auth status` style probe)."""
        try:
            p = await asyncio.create_subprocess_exec(config.CLAUDE_BIN, "--version", stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE)
            out, _ = await asyncio.wait_for(p.communicate(), 20)
            signed_in = (Path.home() / ".claude" / ".credentials.json").exists()
            return {"installed": True, "version": out.decode().strip(), "signed_in": signed_in}
        except Exception as e:
            return {"installed": False, "error": str(e)}


async def oneshot(prompt: str, model: str = "haiku", timeout: float = 180, system: str = "") -> str:
    """A separate, stateless `claude -p` call for background work (meeting titles and summaries) that must not
    enter the spoken conversation. Returns "" on any failure."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    args = [config.CLAUDE_BIN, "-p", "--output-format", "text", "--model", model,
            "--tools", "", "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config"]
    if system:
        args += ["--system-prompt", system]
    try:
        proc = await asyncio.create_subprocess_exec(*args, cwd=config.CLAUDE_WORKDIR, env=env, stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=timeout)
        if proc.returncode != 0:
            log.warning("oneshot failed (%s): %s", proc.returncode, err.decode(errors="replace")[:200])
            return ""
        return out.decode(errors="replace").strip()
    except Exception as e:
        log.warning("oneshot: %s", type(e).__name__)
        try:
            proc.kill()
        except Exception:
            pass
        return ""
