# Validation report — 4 November 2026

Source preview: **1.1.0-dev**. This report distinguishes verified behavior from deployment prerequisites. It is not an App Store approval, a five-hour endurance certification, or validation of unconnected boards.

Final connected firmware image SHA-256 (private configuration): `4357084bdfbad1d8c121d3dc5035ae787897fb56778d540e1056d8790f3c8769`. After moving meeting transport buffers to PSRAM, the final physical smoke test reported approximately 35 KB free internal heap and passed capture/stop/connectivity/lock checks.

## Passed

| Area | Evidence |
|---|---|
| Hub regression suite | 71 tests passed: authorization, sessions/context storage, character generation/validation, Web authentication, voice/display routing, meetings, cloud failure retention, APNs signing/retry/deduplication |
| iOS UI | All 8 simulator tests passed in one full run; final meeting-library changes passed a targeted rerun |
| iOS packaging | Unsigned Release archive succeeded; production push environment, bundled privacy manifest and display name Wappai verified; broad WKWebView arbitrary-load exception absent |
| Firmware | Private and sanitized public 1.75C builds succeeded; app-only physical flash verified by esptool after backup and partition checks |
| Synthetic Hebrew meeting | Actual Hub TTS → ADPCM → recording/STT → isolated summary: 98 chunks, duplicate/resend plus reconnect; exactly 12.456 seconds, nonempty Hebrew transcript and summary, playable audio |
| Physical microphone | A short device recording saved audio; stop, lock and refusal to start while locked checked over USB and authenticated HTTP (409) |
| Extended disconnect | Actual device recorded 133.184 seconds including a 103-second Hub outage. Bounded capture stopped before buffer overflow, resumed upload after reconnect, produced playable 543603-byte audio, and reported `device_buffer_full` with **0 dropped bytes** |
| Power behavior | After buffered upload completed, the device returned to screen-off, 80 MHz low-power state. Pending audio now prevents ordinary deep sleep; critical-battery protection still takes priority |
| Timer event | A real six-second device timer was acknowledged, completed and delivered its persistent timer event to the Hub |
| APNs protocol | An isolated test generated an EC signing key, verified ES256 JWT and sandbox endpoint/topic/headers, simulated success and ensured one delivery per event; failure, retry, stale token and opt-out tests passed |
| Cloud adapter | Mocked private-S3 upload verification/deletion and failed-upload retention passed; local files are not evicted on failure |
| Recovery | Journal test rolls back an unacknowledged append without duplicating duration; out-of-order chunks stop safely; long transcript test covers middle content when live summaries were absent |
| Audio failures | Failed encoding preserves original WAV. Multiple surviving parts are exposed separately rather than misrepresented as a complete final file |
| Graphics | Cached ring AA/bounds, shake gate/cooldown, and 3 character rigs × 39 states across display geometries passed native C++ regressions |
| Web | Library, transcript, explicit consent, offline-device error, 390 px and 320 px layouts checked in Chrome; no horizontal overflow at these widths |
| Desktop launcher | Python/Tk imports and doctor checked on macOS. GUI process started; visual inspection was blocked when the Mac locked. Windows/Linux GUI are not validated |
| Published policy | Site version 8 includes meeting recordings, selected AI providers, optional buckets, APNs tokens, deletion and retention; links to the new guide |

The guide's UI images are real screenshots with deliberately synthetic example content. The device image is a real framebuffer capture. No private conversations or credentials are included.

## Not yet verified / release gates

- No APNs signing key/capability was supplied to this Hub, and the iPhone was unavailable. Real delivery in foreground/background/terminated states, token rotation and signed TestFlight installation remain untested.
- A public App Store app needs a publisher-operated protected push relay. The open-source Hub supports direct APNs for individually signed deployments; publisher keys must never be shared with self-hosting users.
- No real cloud bucket was configured. Live upload, provider encryption support, lifecycle/versioning, quotas and failure recovery must be validated against the selected provider before enabling eviction.
- Only the silver 1.75C is physically qualified here; it has no TF slot. SD code is gated. Other boards require verified BSPs, pin maps, card insertion/removal/full/error tests, retention management and power-cycle upload recovery before distribution.
- The desktop launcher is source-based Python/Tk, not signed/notarized Mac/Windows installers or a Linux package. Tailscale stays a separately installed official client; the computer must remain awake. ESP32 itself uses LAN.
- Five-hour recordings, prolonged battery runtime, low-voltage interruption and every router/card combination were not tested. A no-SD power loss can lose audio still buffered in RAM.
- The current public binary remains 1.0.0-dev.1. New features are in source preview 1.1.0-dev and the owner's updated device/Hub; do not claim the old downloadable image contains them.
- App Store submission still needs the publisher account, signed archive, App Store Connect validation, privacy answers, reviewer access/hardware video and physical-device testing. Approval is Apple's decision.

See [setup guide](END_USER_GUIDE.he.md), [architecture](MEETINGS_ARCHITECTURE.md) and [App Store checklist](APP_STORE_READINESS.md).
