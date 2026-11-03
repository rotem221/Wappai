# Wappai landing page

Compact Hebrew RTL one-page product site, with interactive Three.js presentation models,
real screenshots, public source and development release downloads.

Serve `site` over HTTP. Buildless HTML/CSS/JavaScript; all visual dependencies are local.
Three.js 0.180.0: see `vendor/three/LICENSE`.

Public source: https://github.com/rotem221/Wappai/tree/main/site

## Capture provenance

The three `device-{happy,thinking,dizzy}.png` assets were captured directly from the connected Waveshare 1.75C framebuffer over USB on 2026-11-03, using its existing debug display commands. They are real firmware renders; the device was not reflashed. These unretouched frames remain available in the gallery. The rotating models now use the animated presentation renderer described below. The 1.8/2.16 screens are explicitly labeled interface previews, not validated board firmware.

`ios-chat.png` is a screenshot of the production SwiftUI views running in an isolated iOS simulator Debug build with a sample local conversation; no live account messages are published. `ios-voices.png` and `web-chat.png` are actual application QA captures. Gallery captions explain each source.

Assistant, Gveret Levin, Heebo and Manrope are served locally, licensed under the SIL Open Font License; see `fonts/*-OFL.txt`.

## Animated product studio (version 3)

The landing page rotates through three presentation models and six feature scenes: talking, thinking, weather, timer, home control, and dizzy expressions. `screen-demo.js` uses the original production pixel artwork, motion timings and spiral-eye anchors, with illustrative interface data. It makes no calls to a device, AI provider or home-control service. The page labels the animated screens as demos; original USB/native/Web captures remain in the gallery. 1.8/2.16 firmware is still in preparation.

Models change every 12 seconds, scenes every 5 seconds. Manual selections hold for 12 seconds; pause stops the scene clock and automatic changes. Reduced-motion preferences start paused, and hidden tabs do not render. Canvas textures update at up to 24 fps, with the WebGL renderer capped at 30 fps.

Product preview treatments use CSS lighting, gradients, perspective and shadows around the real screenshots, without altering their image pixels. The GitHub mark comes from Simple Icons (CC0-1.0); its license is in `assets/icons/LICENSE.md`. Other interface icons are project-authored SVG.

## Typography and information pages (version 4)

Hebrew interface copy uses locally hosted Assistant, with Gveret Levin for short handwritten accents. Both come from the official Google Fonts repository under SIL OFL 1.1. Manrope remains the Latin wordmark. The shared responsive footer links to static, JavaScript-independent terms, privacy and accessibility pages. These describe the current demo site and independent self-hosted product; they do not claim a formal accessibility certification. Public GitHub Issues is the listed contact channel; no private personal contact details are published.

Verified desktop (1800 px), mobile (390 px), narrow layout (320 px), legal navigation via keyboard, dialog Escape, internal asset links and HTTP responses. Legal content must be reviewed when hosting, data collection, distribution or contact channels change.

## Simplified opening (version 5)

The opening now has a two-line Gveret Levin handwritten headline, one short description and one downloads action. Firmware, iOS and source links are grouped in the existing dialog. The six scene pills and duplicate download/source links were removed from the intro; automatic examples and the next/pause/model controls remain in the product studio. Sriracha is the locally hosted Latin wordmark across the landing page, footer and information pages (SIL OFL 1.1, official Google Fonts upstream).

Verified desktop, 390/320-pixel layouts, the combined downloads dialog, keyboard Escape and next/pause animation controls. No console errors or horizontal document overflow.

## Browser installation (version 6)

`flash.html` provides browser USB installation for the validated Waveshare 1.75C only. ESP Web Tools 10.4.0 is vendored locally with dependency license notices. The shipped public factory image is SHA-256 verified against `release-config.js`, checked for size/chip header, and installed from the same verified in-memory bytes. The user confirms board/backup before seeing the connect control. Upstream presents erase choice and final installation confirmation; no automatic full-chip erase is configured. The page makes clear that the factory address range can overwrite settings and that browser backup is not provided. Hub/Wi-Fi provisioning remains in the setup guide; no Improv support is implied.

`release-config.js` contains `appStoreUrl: null`. Replace it with the actual `https://apps.apple.com/.../id...` listing after publication. Until then the UI shows a non-link “בקרוב ב־App Store”; no unsigned IPA is offered in the site UI. Developer artifacts remain in GitHub Releases. Keep the terms/privacy/accessibility pages in sync when this changes.

Validation: `node --test tests/web-install.test.mjs` covers release checksum, truncation, mutation, wrong chip header, manifest constraints and store URL validation. Browser QA exercised initial verification, board-confirmation gating, a deliberately corrupted local file (blocked), successful retry after restoring the original, and narrow-screen layout. No actual USB flash was performed for this website change.
