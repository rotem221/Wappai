# Shared controls and display layouts

The device uses lightweight vector fills: surface `#172536`, raised `#253b54`, border `#496783`, accent `#a4d2ff`. Native iOS retains system glass/material controls with a slate-blue tint; Web and landing use the matching light palette. Destructive actions remain red and success status remains green. Reduced motion disables decorative transitions.

Device horizontal page transitions use a 180 ms ease-out, with one temporary previous framebuffer in PSRAM and a cached destination. The buffer is freed at completion/cancellation; transitions are skipped during recording, speech playback, asset transfers and reduced motion. Resting frame-rate and sleep policy are unchanged. A 16 ms target is not a claim of sustained 60 FPS on hardware.

The browser presentation renderer `server/sim/device-ui.js` has independent native layouts for round 466×466, rectangular 368×448 and square 480×480. The same module is used by the landing. Analog faces preserve a circle, tall screens get a separate date row, and controls use shape-specific margins. Other boards remain blocked in the firmware catalog until physical BSP qualification.

Six clock faces and three native profiles were visually inspected. See `qa/style-system-2026-11-05/profiles.png`. Original artwork; Apple/Rolex references inform layout only, with no copied logos or branded face assets.
