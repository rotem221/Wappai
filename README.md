<div align="center">
<img src="assets/brand/wappai-screen-mark.png" width="120" alt="Wappai logo">
<h1>Wappai</h1>
<p>A little companion. An open world of possibilities.</p>
<p>Hebrew-first pocket AI · ESP32-S3 · SwiftUI · Web · Claude / Codex</p>
</div>

Wappai puts an expressive pixel companion on a small touchscreen. Hold BOOT to talk, release to send, and continue the same conversation on iPhone or in your browser. Run the brain on your own Hub and choose the tools and voices it uses.

**[מדריך מלא בעברית](docs/END_USER_GUIDE.he.md)** · **[Get started](docs/GETTING_STARTED.md)** · **[Downloads](https://github.com/rotem221/Wappai/releases)** · **[Project site](https://wappai-companion.rotem221.chatgpt.site)**

## What's inside

- Animated Pip, Nori and Orbit characters; generated custom characters with an approval preview, expression library, spiral dizziness and optional sounds.
- Hebrew speech with English recognition support; Claude Code/Codex adapters, Edge TTS and optional ElevenLabs voice selection.
- A native iOS app and responsive RTL Web chat: synchronized conversations, themes, floating character, device settings and Bluetooth Wi-Fi onboarding.
- Battery-aware rendering, inactivity dimming, persistent lock, hold-to-talk, and configurable shake response.
- Personal Hub integrations such as weather, timers and optional Home Assistant, with room-specific control feedback.

## Current source preview (1.1.0-dev)

The current source adds a meeting library in iOS/Web, acknowledged audio chunks with reconnect recovery, optional private S3 archiving, opt-in APNs notifications, and a source-based desktop Hub launcher. See the [architecture](docs/MEETINGS_ARCHITECTURE.md), [validation report](docs/VALIDATION-2026-11-04.md), and [App Store gates](docs/APP_STORE_READINESS.md). These changes are not included in the older downloadable release below. SD-capable boards are still withheld pending board-specific implementation and physical validation. Actual APNs and cloud delivery require your configured services; no publisher Push relay is included.

## Release status

This is **v1.0.0-dev.1**, an open-source development release. The downloadable firmware targets **Waveshare ESP32-S3-Touch-AMOLED-1.75C** only. The 1.8 and 2.16 presentation models prepare for future support; do not flash this release onto them. Wi-Fi is 2.4 GHz.

The iOS `.ipa` is unsigned and requires personal signing, or an Xcode build with your own team. An App Store release is planned. A personal Hub is required; no shared cloud account or credentials are bundled.

| Directory | Purpose |
|---|---|
| `firmware/` | PlatformIO firmware and shared character renderer |
| `server/` | Python Hub, speech, integrations and Web chat |
| `ios/Piko/` | SwiftUI Wappai app (legacy project name retained) |
| `assets/`, `character/` | Original brand and character artwork/data |
| `tools/` | Build, asset, diagnostic and release helpers |
| `site/` | Compact product landing page and interactive device models |

The public history starts from a sanitized snapshot. Private keys, personal endpoints, device backups and the original development history are intentionally absent. Configure your own Hub using the guide above.

MIT for original code/artwork; see [third-party notices](THIRD_PARTY.md) for fonts, frameworks and dependencies. Independent project; not affiliated with Waveshare, Apple, OpenAI, Anthropic or ElevenLabs.
