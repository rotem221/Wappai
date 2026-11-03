# Device ↔ server protocol (v1)

WebSocket `wss://<server>/ws` (Tailscale Funnel) or `ws://<lan-ip>:8770/ws`.
Auth: `Authorization: Bearer <DEVICE_TOKEN>` header (board) or `?token=` (simulator). Wrong token → close 4401.
Text frames = JSON with `type`. Binary frames = PCM s16le, 16 kHz, mono, ≤2048 bytes.

## Device → server
| type | fields | meaning |
|---|---|---|
| `hello` | device_id, fw_version, name, screen, has_mic, has_speaker, battery{pct,mv,charging,usb} | first message |
| `ptt_start` | id, sample_rate | push-to-talk pressed; binary mic frames follow |
| `ptt_end` | id | released; server transcribes and answers |
| `text` | text | typed question (simulator / tests) |
| `interrupt` | – | user hushed it (short BOOT press / swipe down) |
| `touch` | gesture (`tap`), x, y | petting etc. |
| `event` | name (`timer_done`, `shake`), label? | local happenings |
| `status` | rssi, heap, uptime, battery | every 60 s |
| `pong` | t | answer to ping |

## Server → device
| type | fields | meaning |
|---|---|---|
| `ping` | t (epoch) | every 30 s; device sets its clock + RTC |
| `state` | emotion?, gesture?, ring? (`think`/`none`) | face / ring change |
| `say` | id, seq, text, emotion, audio | a sentence; if `audio`, binary PCM follows. seq 0 starts a new utterance (cuts playback), seq>0 appends |
| `audio_end` | id, seq, final | end of a sentence's audio; `final:true` = utterance done |
| `heard` | text | what STT understood (simulator shows it) |
| `timer` | id, seconds, label | start a device-side timer (works offline, survives screen-off) |
| `timer_cancel` | – | |
| `stop` | – | stop playback now |
| `ota` | url | download firmware and reboot |
| `config` | brightness? | runtime settings |

## Reply format from the brain (parsed by `server/app/brain/reply.py`)
`[emotion]` tags, `<gesture name="nod"/>`, `<timer seconds="300" label="פסטה"/>`, `<timer_cancel/>`.
Everything else is speech, split into sentences and synthesized one by one so audio starts early.


### Wappai display and speech additions

- `config.live_transcription` (boolean, default false): show provisional Hebrew transcript during local push-to-talk. Persisted with device UI settings.
- `transcript.partial`: `{text, capture_id?}`. Ephemeral, no native-client replay cursor and no chat-history row. Empty text clears the draft. The board ignores nonempty text unless recording and the setting is enabled. Clients must accept cursorless events without advancing their durable cursor.
- `interaction`: `{text, clear_card}`. Short visible processing status; clears the previous card when a new turn starts. This is a status label, not hidden model reasoning.
- `device.badge`: `{dev:{id,name,kind,on,state,available}, pending, ttl}`. Compact informational status over the character; no control command. Pending is not confirmation of success.
- Authenticated native voice endpoints: `GET/POST /v1/voice` for status/selection; `POST /v1/voice/connect` with an API key; `POST /v1/voice/search` with `search` and optional `cursor`; `POST /v1/voice/preview` with voice/model/style returns a short WAV. Credentials remain server-side. Existing device audio remains 16-bit mono PCM at 16kHz.
