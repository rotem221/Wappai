"""Settings from environment / .env (see deploy/companion.env.example)."""
import os
from pathlib import Path


def _load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


ROOT = Path(__file__).resolve().parent.parent
_load_env(Path(os.environ.get("COMPANION_ENV", "/etc/companion.env")))
_load_env(ROOT / ".env")


def env(name, default=""):
    return os.environ.get(name, default)


HOST = env("HOST", "0.0.0.0")
PORT = int(env("PORT", "8770"))
DEVICE_TOKEN = env("DEVICE_TOKEN")              # shared secret for devices and the simulator
PUBLIC_URL = env("PUBLIC_URL", "")              # e.g. https://piko.tailXXXX.ts.net
LAN_IP = env("LAN_IP", "192.168.1.10")
TZ = env("TZ", "Asia/Jerusalem")

# character
NAME = env("COMPANION_NAME", "ואפאי")
OWNER = env("COMPANION_OWNER", "")
LANG = env("COMPANION_LANG", "he")
STT_LANGUAGE = env("STT_LANGUAGE", "auto")
RETAIN_DEBUG_AUDIO = env("RETAIN_DEBUG_AUDIO", "0") == "1"
TTS_PROVIDER = env("TTS_PROVIDER", "edge")
TTS_STYLE = env("TTS_STYLE", "lively")
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = env("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL = env("ELEVENLABS_MODEL", "eleven_v3")

# brain: "claude_cli" (Claude Code, signed in with your subscription) or "api" (ANTHROPIC_API_KEY)
BRAIN = env("BRAIN", "claude_cli")
CLAUDE_BIN = env("CLAUDE_BIN", str(Path.home() / ".local/bin/claude"))
CLAUDE_MODEL = env("CLAUDE_MODEL", "haiku")
CLAUDE_WORKDIR = env("CLAUDE_WORKDIR", str(Path.home() / "brain"))
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
API_MODEL = env("API_MODEL", "claude-haiku-4-5")

# speech
STT_ENGINE = env("STT_ENGINE", "stream")        # "stream" (zipformer, fast) or "whisper" (large-v3-turbo, slower, most accurate)
STREAM_MODEL_DIR = env("STREAM_MODEL_DIR", str(Path.home() / "models/zipformer-he"))
STT_MODEL = env("STT_MODEL", "ivrit-ai/whisper-large-v3-turbo-ct2")
STT_THREADS = int(env("STT_THREADS", "4"))
TTS_VOICE = env("TTS_VOICE", "he-IL-HilaNeural")   # or he-IL-AvriNeural
TTS_RATE = env("TTS_RATE", "+8%")

# context
LAT = float(env("LAT", "32.0853"))
LON = float(env("LON", "34.7818"))
CITY = env("CITY", "תל אביב")

# Home Assistant (optional; used through Claude's MCP)
HA_URL = env("HA_URL", "")
HA_TOKEN = env("HA_TOKEN")

FIRMWARE_DIR = Path(env("FIRMWARE_DIR", str(ROOT / "firmware_dist")))
DATA_DIR = Path(env("DATA_DIR", str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
