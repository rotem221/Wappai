# Hebrew speech and response time — 4 November 2026

## Behavior

- Added independent user address and character self-reference preferences in iOS and Web voice settings. Unknown address preferences use neutral wording and prompt for a choice after the answer; meeting-start announcements are exempt. The question is not repeated while it remains in the current conversation history.
- A direct reply such as “נקבה”, “בלשון זכר”, or “אני מעדיפה בלשון נקבה בבקשה” after that question is persisted. Explicit commands such as “פנה אליי בלשון זכר” can also change it. Names, voice identity, quoted text and the gender used to address the assistant do not implicitly set the user's preference.
- Preferences are injected on every turn. Claude's process is renewed on the next turn when they change, so its original system instructions cannot retain a conflicting preference. Durable session history is still injected after renewal.
- Neutral phrasing replaces gendered built-in speech errors and the voice preview. Ordinary answers no longer receive a forced excited audio tag. Hebrew text supplies `language_code=he`; English-only replies do not force Hebrew.

## Latency work

- Reuse a lifecycle-owned HTTP/2 connection pool for speech; close it on server shutdown. Streaming forwards sample-aligned 2,048-byte chunks.
- Hebrew recognition finalization and English recognition run concurrently. The English detector skips lazy Whisper segment decoding when the language is not English; that duplicate Hebrew result was previously discarded. English still receives full transcription.
- Ordinary questions do not block on cold weather or unrelated calendar lookups. Explicit weather/calendar requests still obtain the relevant context.
- The personal Hub retains the pre-existing selected Chen Levi voice (confirmed unchanged against the restore point) and now uses `eleven_v4_turbo`, verified in the account's Hebrew-capable model list. The source default remains unchanged for other installations; users can select an available model in voice settings.

## Validation

105 server tests passed, plus the isolated production conversation pipeline: home-device/weather separation, preference question, persistence, no repeat after selection, current prompt preference, and concurrent English recognition. iOS Debug built with Push entitlements and was installed on the physical iPhone. The deployed Web preferences were visually inspected.

Live Claude checks produced separate correct forms for a feminine user/masculine character and a masculine user/feminine character. A neutral-language probe initially used a gendered plural; the instruction was tightened and the repeat produced “אפשר להתחיל” without gendered readiness wording. These are sample checks, not a guarantee that a language model can never make a grammar mistake.

The same generated Hebrew recording was streamed through the deployed push-to-talk path before and after the changes. Each pair used a new temporary conversation, then a follow-up; the original conversation was restored and test conversations removed.

| Time from recording release to first PCM at the test client | Before | After |
| --- | ---: | ---: |
| First turn in the test conversation | 4.144 s | 2.642 s |
| Follow-up turn | 3.073 s | 2.102 s |

This is a two-sample comparison, with variable cloud/agent latency and different generated reply wording. It measures first streamed PCM, not the physical speaker's playback-buffer delay. The physical ESP32 was absent from USB and the Hub at final verification; actual microphone/speaker quality and battery endurance were not requalified in this change. Firmware and device power policy were unchanged.

An attempted shorter recognizer tail padding truncated the final words of a sample. It was rejected; the existing padding remains intact.

## Physical speaker follow-up

After the device was reconnected by USB, the `ws-s3-175c` was detected by the Hub with 91% battery and USB charging. The first serial-monitored request did not play: the board had restarted (uptime zero) and was still joining Wi-Fi. The repeat waited for both Wi-Fi and Hub connectivity before sending the same ready-made Hebrew sentence.

The speaker task reported playback start **0.523 seconds** after the HTTP request began. Serial telemetry confirmed `playing=1` during playback, then `playing=0`, an idle expression, and continued Wi-Fi/Hub connectivity. The microphone receiver remained off during this output-only check. The board also entered its existing screen-off/80 MHz idle state while awaiting the connection and woke for playback.

This verifies delivery to the physical playback task and completion, not acoustic clarity or freedom from audible artifacts. It excludes microphone capture, transcription and model reasoning, so it must not be compared directly with the full-turn latency table above. No firmware or power settings were changed. Subjective speaker quality and a fresh physical BOOT/microphone conversation still require a listening test; battery endurance was not measured.

## Restore points and references

- Private Git tag: `backup/pre-speech-clarity-20261104`.
- Personal Hub source/settings backup: `/var/backups/wappai/20261104-speech/`.
- [ElevenLabs streaming request and language control](https://elevenlabs.io/docs/api-reference/text-to-speech/stream)
- [ElevenLabs models and supported languages](https://elevenlabs.io/docs/overview/models)
- [Sherpa streaming example and tail padding](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/online-decode-files.py)
