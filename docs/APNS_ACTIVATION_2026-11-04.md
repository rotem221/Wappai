# Apple Push activation — 4 November 2026

## Completed

- Registered two dedicated APNs signing keys in Apple Developer: one Sandbox, one Production. Each is topic-restricted to `com.dadon.wappai`; unrelated apps and their keys were unchanged.
- Stored the downloaded private keys outside both source repositories. Local files are mode `0600` in a `0700` directory. Server key files are mode `0600`, owned by the service account, in a restricted directory. No private key is embedded in the application or committed to Git.
- Added a dedicated systemd environment file and drop-in to the personal Hub, preserving existing voice, network and AI settings. Backed up service configuration, environment files and the notification database before activation. Restarted the service successfully.
- Generated an explicit development provisioning profile for the application, built with automatic provisioning, and verified `aps-environment=development` and the matching application environment. Installed and launched that build on a physical iPhone. The old wildcard-signed build did not have Push permission.

## Verification

- 48 focused automated tests passed during setup. These are software tests, not physical notification delivery tests.
- Both configured private keys parse correctly; ES256 signing and verification against their public keys pass.
- Both Apple gateways are reachable from the Hub over TLS and HTTP/2. A root-path request receives HTTP 405 as expected for that unsupported operation. This only verifies transport, not provider authorization or delivery.
- The Hub health check passes and the ESP32 reconnected after the restart.

## Remaining physical checks

At the last check, the notification registry contained no iPhone registration. The user must enable notifications from Wappai settings and accept the iOS permission prompt. iPhone Mirroring was unavailable because the phone microphone was in use.

Once registered, trigger a timer and verify both APNs acceptance (`sent` outbox entry) and visible arrival. Repeat in the foreground/background, check meeting and Pip completion links, and verify opt-out. Production delivery requires a distribution/TestFlight build and a production device token; the installed development build exercises Sandbox only.

## Operating notes

- The existing worker delivers timer, completed-meeting, Pip-preview and completed-Pip notifications. Payloads contain generic event text, not meeting transcripts.
- This is an owner-operated deployment. Do not distribute these keys to other self-hosted installations. A protected publisher push relay is still required before offering shared App Store Push to arbitrary customer Hubs.
- Server configuration: `/etc/wappai-apns.env`; systemd drop-in: `/etc/systemd/system/companion.service.d/apns.conf`; private keys: `/etc/companion/apns/`.
- Restore point: `/var/backups/wappai/20261104-apns-activation/`. Reverting the drop-in requires a systemd daemon reload and service restart. Preserve the new keys securely unless deliberately revoking them in Apple Developer.

No App Store upload, review approval or actual push delivery is claimed by this activation record.
