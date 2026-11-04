# Hub readiness and recording verification — 4 November 2026

## Changes

- APNs now accepts separate sandbox and production signing keys, with legacy dual-environment configuration retained. Incomplete scoped configuration fails closed; registration reports readiness for the phone's actual environment.
- Provider JWTs are reused for 50 minutes, within Apple's 20–60 minute refresh interval. HTTP/2 clients are reused separately per environment, recreated when key configuration changes, and closed on worker cancellation.
- The desktop launcher waits for a valid local health response before reporting readiness. Occupied ports, early process exits and startup timeouts are reported; failed child processes are cleaned up. Local health checks bypass inherited proxy settings, and the log is private on POSIX systems.
- Optional cloud cache eviction verifies the final archive's current bucket, object metadata, size and local checksum before deleting audio. It requires a saved nonempty transcript. Missing/changed objects or credentials retain the local recording; cleanup failure does not block transcription or summary completion.
- The Hebrew setup guide explains that recordings already stream to the owner's Hub and that a cloud bucket is optional, and documents the new APNs configuration.

## Verified

- **93 Python tests passed** across the Hub, including six cloud eviction scenarios, signed APNs requests, separate key routing, JWT refresh, connection reuse/rotation, and launcher startup failures.
- Live synthetic Hebrew meeting on the deployed Hub: **98 chunks, 12.456 seconds**, with an intentional duplicate and WebSocket reconnect. The result reached `done`, preserved the exact duration, and produced playable audio, a 135-character transcript and a 532-character summary. This test used generated speech, not private microphone audio.
- macOS launcher doctor confirmed Python 3.12, FFmpeg, Tailscale and Codex availability. A GUI process was started and stopped, but the native automation service could not attach to its window; no visual GUI pass is claimed.

## Restore points

- Private Git tag: `backup/pre-apns-setup-20261104`.
- Private Hub backup: `/var/backups/wappai/20261104-apns-readiness`, containing source and consistent SQLite backups before deployment.

## Still pending

- The user explicitly deferred Apple Developer login and actual APNs activation. No Apple key, Push-enabled signing profile or App Store upload was created in this stage. Actual iPhone delivery remains unverified.
- No external cloud bucket has been provisioned or configured. Cloud failures and verification are covered by isolated tests, not a live provider integration.
- The ESP32 was absent from the Hub and USB inventory during this stage. No new firmware was flashed; battery behavior and hardware recording were not requalified here.
- Windows/Linux GUI, signed desktop installers, other Waveshare boards, prolonged recording/battery endurance and App Store acceptance remain subject to the earlier release gates.

## References

- [Apple: APNs token authentication and key environments](https://developer.apple.com/documentation/usernotifications/establishing-a-token-based-connection-to-apns)
- [Apple: APNs connection reuse](https://developer.apple.com/documentation/usernotifications/establishing-a-connection-to-apns)
