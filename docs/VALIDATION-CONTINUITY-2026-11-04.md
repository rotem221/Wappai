# Conversation, timer and meeting validation — 2026-11-04

- Live Claude and Codex sessions each accepted an initial value and correctly recalled it in a follow-up. Both retained two user and two assistant messages. First responses completed in 5.12/7.30 seconds; follow-ups in 4.81/4.26 seconds, including generated speech. These are individual test observations, not latency guarantees.
- A six-second timer was requested through the conversation API. The actual board progressed to `alarm=1` with playback, and a short-button diagnostic dismissed it (`alarm=0`). Wi-Fi and Hub remained connected throughout the observed conversation/timer sequence.
- A synthetic Hebrew meeting exercised 67 ADPCM chunks, duplicate delivery and WebSocket reconnect/replay. Durable acknowledgements succeeded. The final 8.56-second duration matched the unique input samples, with no duplicated audio duration. Final state was `done`, with 137 transcript characters, 498 summary characters and a saved audio file.
- Removed only the newly created QA conversations and synthetic meeting. Restored the original active conversation. No personal recording was captured or deleted.
- The final live API reported the board online, ElevenLabs configured with the selected voice, and no meeting recording in progress.

## Deployment gaps confirmed

- APNs is not configured in sandbox or production. Real iPhone push delivery is therefore not yet available; queue/API unit coverage is not evidence of APNs delivery. Apple account setup was previously deferred by the owner.
- The meeting store is currently Hub-local, with a 4 GiB quota. A cloud bucket is not configured, so cloud archival has not been validated in this deployment. The API reported 66,935 seconds of aggregate free recording capacity under its conservative estimate, with a separate five-hour per-session cap.
- The connected 1.75C reports no SD slot and a 98-second offline audio-buffer capacity. No claim is made for SD-equipped hardware or for recordings surviving a longer network loss on this board.
- No physical iPhone gestures or battery discharge test were repeated. Context across a full Hub restart was not exercised in this pass.

Private evidence: `~/.cache/wappai-build/continuity-qa-20261104/`.
