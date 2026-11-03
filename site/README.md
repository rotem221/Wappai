# Wappai landing page

Compact Hebrew RTL one-page product site, with interactive Three.js presentation models,
real screenshots, public source and development release downloads.

Serve this directory over HTTP. Buildless HTML/CSS/JavaScript; all visual dependencies are local.
Three.js 0.180.0: see `vendor/three/LICENSE`.

Public source: https://github.com/rotem221/Wappai/tree/main/site

## Capture provenance

The three `device-{happy,thinking,dizzy}.png` assets were captured directly from the connected Waveshare 1.75C framebuffer over USB on 2026-11-03, using its existing debug display commands. They are real firmware renders; the device was not reflashed. These unretouched frames remain available in the gallery. The rotating models now use the animated presentation renderer described below. The 1.8/2.16 screens are explicitly labeled interface previews, not validated board firmware.

`ios-chat.png` is a screenshot of the production SwiftUI views running in an isolated iOS simulator Debug build with a sample local conversation; no live account messages are published. `ios-voices.png` and `web-chat.png` are actual application QA captures. Gallery captions explain each source.

Heebo and Manrope are served locally, licensed under the SIL Open Font License; see `fonts/*-OFL.txt`.

## Animated product studio (version 3)

The landing page rotates through three presentation models and six feature scenes: talking, thinking, weather, timer, home control, and dizzy expressions. `screen-demo.js` uses the original production pixel artwork, motion timings and spiral-eye anchors, with illustrative interface data. It makes no calls to a device, AI provider or home-control service. The page labels the animated screens as demos; original USB/native/Web captures remain in the gallery. 1.8/2.16 firmware is still in preparation.

Models change every 12 seconds, scenes every 5 seconds. Manual selections hold for 12 seconds; pause stops the scene clock and automatic changes. Reduced-motion preferences start paused, and hidden tabs do not render. Canvas textures update at up to 24 fps, with the WebGL renderer capped at 30 fps.

Product preview treatments use CSS lighting, gradients, perspective and shadows around the real screenshots, without altering their image pixels. The GitHub mark comes from Simple Icons (CC0-1.0); its license is in `assets/icons/LICENSE.md`. Other interface icons are project-authored SVG.
