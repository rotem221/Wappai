# End-to-end validation after Pip connection recovery — 2026-11-04

## Passed

- All 100 server tests: client/device authentication, conversations and context, Pip lifecycle and protected defaults, image input validation, approval, notifications, meetings, voice routing and display intents. One test-library deprecation warning remains; no failures.
- AddressSanitizer/UndefinedBehaviorSanitizer native checks: built-in renderer, circular and rounded-rectangle rings, sparse display transfers, shake gating, power policy, custom pack validation/corruption rejection, and spiral eyes. The custom-pack tests used the newly generated real pack.
- Swift pairing policy tests: restored Wi-Fi, duplicate discovery, join acknowledgement, verified-offline prompts and suppression while online, backgrounded or already dismissed.
- iOS simulator Debug build succeeded with the current source. This was a build check, not a new physical touch/swipe acceptance test.
- A temporary QA copy of the already generated preview went through the real Hub approval endpoint, Codex atlas generation, compilation, gallery publication and hardware installation. Completed in 60.1 seconds: 24 poses, 43 motion sequences, 100,036-byte package, matching SHA-256, and physical device `applied` acknowledgement. The generated atlas was visually inspected.
- Restored the original selected character, removed only the temporary QA character and verified the original gallery IDs and active conversation were unchanged. The user's pending preview remains unchanged and awaits their approval.
- ElevenLabs / Rotem Dadon / Eleven v3 produced 120,320 bytes of 16 kHz mono PCM, with a normal audio-end event. USB diagnostics observed playback start and finish while Wi-Fi and the Hub remained connected. This verifies playback execution, not a human listening-quality rating.
- Device lock kept the screen off, CPU at 80 MHz and microphone RX disabled. Injected shake samples did not wake or play while locked. Unlock and speaker-to-microphone tone checks succeeded; microphone RX returned to disabled afterwards.
- Device battery reported 92% and charging over USB at the start. Original custom character storage remained intact.

## Boundaries

No firmware flash or iPhone reinstall was needed. Physical BOOT/PWR switches, a new BLE/password setup, and iPhone touch gestures were not manually repeated. Deep-sleep delays were checked by policy and device diagnostics while USB-powered; battery endurance was not measured. Hardware acceptance covers the connected 1.75C only, not the other board variants. This pass does not complete deferred APNs/App Store account setup.

Private artifacts and logs: `~/.cache/wappai-build/full-qa-20261104/`.
The Hub retains a private pre-test SQLite recovery copy; it was not restored over live data or committed to Git. No API keys or personal images were added to the source repository.
