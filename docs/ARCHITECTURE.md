# Architecture

```
┌──────────── Device: Waveshare ESP32-S3-Touch-AMOLED-1.75 (firmware/) ────────────┐
│ core 1: app/      input (BOOT hold-to-talk, touch, PWR, IMU), power states,       │
│                   device-side timers, drawing                                     │
│         face/     SDF vector character, 39 emotions, springs + blink/gaze/breath  │
│         ui/       edge ring (recording progress / thinking / timer), Hebrew bidi  │
│ core 0: net/      Wi-Fi portal, WSS (Let's Encrypt roots), protocol, mic upload,  │
│                   OTA                                                             │
│         audio/    ES8311 speaker + ES7210 mics @16 kHz, mouth level               │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │ wss://<host>.ts.net/ws   (Tailscale Funnel = public TLS,
                                │                           no VPN client on the device)
┌───────────────────────────────▼──── Server: LXC 2114 on Proxmox (server/) ────────┐
│ FastAPI hub (/ws, /api, /fw, simulator at /)                                      │
│  ptt audio → STT (ivrit.ai Whisper large-v3-turbo, int8 CPU)                      │
│           → context (time, weather Open-Meteo, battery)                           │
│           → brain: Claude Code CLI, persistent stream-json session, own login     │
│                    (or Anthropic API when BRAIN=api)  + MCP (Home Assistant)      │
│           → reply parser ([emotion], <gesture>, <timer>) → TTS per sentence       │
│             (edge-tts he-IL) → PCM back to the device + subtitles                 │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Design rules
- **The device is a body, the server is the brain.** The board never decides what to say; it
  renders, listens, keeps time and saves power. Everything smart can change without reflashing.
- **One character definition** (`character/creature.json`) feeds the firmware (generated C header)
  and the browser simulator, so what you design in the browser is exactly what the board shows.
- **Things that must work offline run on the device:** clock (RTC), timers + alarm, battery, face.
- **Security:** Funnel exposes the server publicly, so every endpoint needs `DEVICE_TOKEN`.
  Claude runs with file/shell tools disabled; only WebSearch and the configured MCP servers are allowed.

## Power states (firmware/include/config.h)
| state | when | what is on |
|---|---|---|
| active | interaction in the last 30 s | screen at full brightness, ~30 fps |
| dim | 30 s – 90 s idle | brightness 30, 15 fps |
| off | 90 s idle, PWR press, or face-down | panel asleep, Wi-Fi modem-sleep, IMU polled 4×/s for pick-up |
| deep sleep | 20 min off **on battery** | everything off; wake: BOOT, touch, or a running timer |

Battery care: AXP2101 charges to **4.1 V** (instead of 4.2 V) at 200 mA.

## Character pipeline
`character/creature.json` → `python3 tools/gen_face.py` → `firmware/src/face/emotions.gen.h` + `server/sim/emotions.json`.
Preview without hardware: `tools/face_preview` (native C++ build of the firmware renderer → PNG/GIF).
