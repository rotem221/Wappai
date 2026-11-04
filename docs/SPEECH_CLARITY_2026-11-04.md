# Hebrew speech and response time — 4 November 2026

## Behavior

- Added independent user address and character self-reference preferences in iOS and Web voice settings. Unknown address preferences use neutral wording and prompt for a choice after the answer; meeting-start announcements are exempt. The question is not repeated while it remains in the current conversation history.
- A direct reply such as “נקבה”, “בלשון זכר”, or “אני מעדיפה בלשון נקבה בבקשה” after that question is persisted. Explicit commands such as “פנה אליי בלשון זכר” can also change it. Names, voice identity, quoted text and the gender used to address the assistant do not implicitly set the user's preference.
- Preferences are injected on every turn. The follow-up below replaces preference-triggered Claude restarts with a stable system policy and current per-turn preferences. Durable session history remains injected for every turn and for idle/turn-limit recovery.
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

## Full acoustic microphone conversation

The user confirmed that the preceding direct speaker sample was clear and pleasant. The next check exercised the physical microphone: the Mac's built-in speakers played two generated Hebrew WAV fixtures aloud, and the ESP32 captured them through its microphone. No input PCM was injected into the server. Serial `bootsim` commands exercised the existing long-press/release BOOT handler; this was not a fresh test of a human pressing the mechanical switch.

Three turns used a temporary Claude conversation. The first asked the assistant to remember a purple umbrella. The next two asked which object had been selected and requested a readiness question addressed according to the user's preference. The same follow-up fixture was used for both address settings.

| Turn | User address setting | Observed answer | Recording end → reply playback |
| --- | --- | --- | ---: |
| Remember the object | Masculine | “זכרתי שהחפץ שבחרת הוא מטריה סגולה” | 8.390 s |
| Follow-up | Masculine | “החפץ שבחרת הוא מטריה סגולה … האם אתה מוכן לצאת איתה?” | 5.284 s |
| Same follow-up after changing preference | Feminine | “בחרת מטריה סגולה … את מוכנה לצאת איתה?” | 8.063 s |

Times use the ESP32's own millisecond timestamps for `ptt: stop` and `spk: on`. Playback events were correlated with the first received answer PCM to exclude both the release chirp and local thinking sounds. An initial diagnostic calculation mistakenly selected the chirp; the table above is the corrected speech measurement. These measurements include microphone buffering, network delivery, recognition, model generation, TTS and device playback buffering. They are not comparable to the 0.523-second ready-text speaker check.

Recognition retained the object and the follow-up question in all three turns. In this baseline, context survived both a follow-up and the Claude process refresh then triggered by changing the preference. Server recognition timing was 1.12–1.33 seconds; logged first-token timing was 4.72–7.41 seconds from the server turn timer (which includes recognition). Model response time was the largest measured wait, with additional transport/buffering variability. Three samples are insufficient for a percentile or general latency guarantee.

The requested masculine/feminine *user address* checks passed. A separate limitation was observed: with character self-reference set to neutral, the masculine-address response included “אני שואל”. The user-facing address was correct, but neutral character self-reference is not fully reliable from prompting alone; do not interpret this test as complete grammatical compliance in every response.

The temporary conversation was deleted, original active conversation and both voice preferences restored and verified via the live API, and the Mac's original muted volume restored. The device remained online with recording off; serial telemetry confirmed the microphone receiver returned to `rx=0`. No firmware, power policy or voice selection was changed. The test validates controlled acoustic input, not the user's natural voice in a noisy room or battery endurance.

## Neutral self-reference and latency follow-up

The previous physical test exposed “אני שואל” with a neutral character setting. The follow-up strengthens the neutral persona and adds narrowly scoped, unquoted self-reference corrections before the sentence is sent to TTS, captions and durable conversation storage. Question introductions become “השאלה שלי היא”; affirmative “אני זוכר/זוכרת” becomes “זכרתי”. User address, quoted wording and negation are preserved. This is a targeted guard for observed failures, not a general Hebrew grammar guarantee.

Claude now uses a stable system policy that delegates the two speech preferences to the current turn's application instructions. Changing a preference no longer restarts its process or discards its native context. The same model, tool permissions, durable conversation injection, idle timeout and turn limit remain in use. Local process startup overlaps microphone capture without sending a model request, speculative answer or synthetic conversation turn. Preparation uses the normal conversation lock and is cancelled when its session is deleted or the service stops.

120 server tests passed, including preservation of quoted/negative text, current preference injection across consecutive turns in one process, no prompt sent during preparation, and continued idle-expiry reset. The isolated production pipeline confirmed identical normalized text in TTS and displayed `say` events, with the existing appliance/weather, onboarding and English-recognition regressions passing.

The same two acoustic fixtures at the same Mac volume were first rerun on the device: reply onset was 6.067 / 3.868 / 5.217 seconds, compared with 8.390 / 5.284 / 8.063 seconds in the baseline. Context and masculine/feminine user address survived, but “אני זוכר” remained in that intermediate version and was then covered by the final guard. Later runs of the final version encountered unrelated background speech and recognition errors; these are retained as diagnostic evidence, not counted as clean speed benchmarks. A further fixture used a shorter follow-up and louder Mac playback, so its timings are not a controlled like-for-like comparison. No percentage speed guarantee is inferred from these small, cloud-variable samples.

Firmware, microphone gain, PCM format, playback buffering, STT decoding/tail padding, selected TTS voice/model and device power policy were unchanged. Mac volume and application speech preferences were restored after each automated run. Restore points: Git tag `backup/pre-mic-latency-20261104` and the private Hub backup `/var/backups/wappai/20261104-mic-latency/`.

Final verification status: all automated physical runs completed microphone capture, recognition, generation and speaker playback, and retained the umbrella context with the configured user address. Unrelated speech was still present in several recordings, including after the user reported readiness for a quiet test. The three inspected YouTube players were paused; no browser playback setting was changed. A manual BOOT test was then armed for five minutes, but no recording was started. It timed out and cleaned up normally: the original active conversation and speech preferences were verified restored through the live API, the temporary conversation was deleted, the device remained online with recording off, and the original muted Mac output volume was restored. A clean final natural-voice latency comparison remains pending; do not describe the noisy final samples as a completed controlled benchmark.

The existing streaming-JSON interface remains in use; see [Claude Code's official programmatic usage documentation](https://code.claude.com/docs/en/headless). Bare mode was not adopted because the documented mode does not use the existing subscription login.

## Restore points and references

- Private Git tag: `backup/pre-speech-clarity-20261104`.
- Personal Hub source/settings backup: `/var/backups/wappai/20261104-speech/`.
- [ElevenLabs streaming request and language control](https://elevenlabs.io/docs/api-reference/text-to-speech/stream)
- [ElevenLabs models and supported languages](https://elevenlabs.io/docs/overview/models)
- [Sherpa streaming example and tail padding](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/online-decode-files.py)
