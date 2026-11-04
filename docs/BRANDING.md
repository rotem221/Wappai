# Wappai pixel branding

The emerald pixel W is the first letter in the Wappai wordmark. Approved transparent logo and symbol masters are in `assets/brand/pixel-source/`; exact imagegen prompts and provenance are in `assets/brand/generation.json`.

Run `swift tools/wappai/prepare_brand.swift` from the repository root on macOS to reproduce the iOS, Web and Hub assets. Packaging trims the wordmark bounds, preserves transparency and uses nearest-neighbor resizing. The 1024px iOS app icon is opaque RGB. A brighter transparent symbol is used on black device-model screens; dark interfaces tint the wordmark silhouette for contrast.

Verification: Release iOS build succeeded and was installed on the paired iPhone. PNG dimensions and alpha channels were checked. Web branding was visually checked in light and dark mode; the landing page was checked at desktop and 390px mobile widths. The website demo screenshot uses isolated sample conversations, not private chats.
