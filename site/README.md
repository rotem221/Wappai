# Wappai landing page

Compact Hebrew RTL one-page product site, with interactive Three.js presentation models,
real screenshots, public source and development release downloads.

Serve this directory over HTTP. Buildless HTML/CSS/JavaScript; all visual dependencies are local.
Three.js 0.180.0: see `vendor/three/LICENSE`.

Public source: https://github.com/rotem221/Wappai/tree/main/site

## Capture provenance

The three `device-{happy,thinking,dizzy}.png` assets were captured directly from the connected Waveshare 1.75C framebuffer over USB on 2026-11-03, using its existing debug display commands. They are real firmware renders; the device was not reflashed. The rotating models display these complete, unretouched frames at their original aspect ratio. The 1.8/2.16 screens are explicitly labeled interface previews, not validated board firmware.

`ios-chat.png` is a screenshot of the production SwiftUI views running in an isolated iOS simulator Debug build with a sample local conversation; no live account messages are published. `ios-voices.png` and `web-chat.png` are actual application QA captures. Gallery captions explain each source.

Heebo and Manrope are served locally, licensed under the SIL Open Font License; see `fonts/*-OFL.txt`.
