# Controls, clock faces and transitions — 2026-11-05

Firmware/source: 1.1.4-dev; public package: 1.1.4-dev.1.

- Known 1.75C: app-only upgrade verified, with all six cached characters and 29 functional USB checks passing. Includes all-page brightness/volume, timer selection, clock chooser, lock/gesture arbitration and 20 bidirectional page transitions.
- Twenty transitions: mean 195.35 ms, range 181–231 ms, mean 7.2 rendered frames. Configured duration changed from 240 to 180 ms. The previous build was not measured with the same instrumentation, so this is not a measured percentage speedup. No 60 FPS guarantee.
- C++ slide compositor: address/undefined sanitizers passed all 933 offsets in both directions and clipped DMA spans. Edge gesture/timer boundary checks passed.
- Public server: 143 tests passed; existing dependency deprecation warning remains. Mocked production control receipt → Hebrew confirmation → PCM pipeline passed without a model/context round trip.
- Web: isolated browser QA passed history, XSS, shared settings, voice error paths, character CRUD/approval, dark/light, RTL/mobile and admin styling. Native profiles: 24 clock/settings/timer combinations at three resolutions; 1440/390/320 layouts without document overflow.
- Native iOS: signed local device build installed; unsigned public Release build passed separately. Physical iPhone UI confirmation was not performed.
- Browser installer: seven image-integrity/board-gating/store-link checks passed; all parts and public catalog hash match. Private credential values were absent in the scanned source and all 18 artifact entries.

Limits: the first USB test stopped on a host log/read timeout; a complete buffered-log rerun passed. 1.8, 2.16 and separate 1.75 hardware are unvalidated and remain blocked for firmware distribution. Factory-reset onboarding, update power-loss recovery, long battery discharge, wake-name acoustics and perceived smoothness were not newly qualified. Prior release/recovery artifacts remain available.
