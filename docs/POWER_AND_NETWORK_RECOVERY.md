# Nearby Wi-Fi recovery and standby power — 2026-11-04

The iOS app now distinguishes authenticated nearby Bluetooth presence from verified Wi-Fi connectivity. While foregrounded it reads device status every 20 seconds (no periodic network scans). A verified offline device gets a 12-second reconnect grace period before the network picker opens. Unknown status, online Hub presence, active joining and other presented sheets suppress the prompt. Dismissal suppresses repeats until Wi-Fi recovers. Backgrounding stops monitoring. Manual settings remain available; successful recovery closes its automatic sheet.

Firmware stops I2S RX DMA when neither recording nor microphone diagnostics need it. The mic task exclusively enables/disables RX, preserving TX/shared clocks and meeting capture. Idle display still dims after 15 seconds and switches off after 30 seconds. On battery, explicit lock or less than 20% charge caps the screen-off-to-deep-sleep delay at 60 seconds; pocket mode caps it at 90 seconds. Shorter configured delays are respected. Recording, pending uploads, playback and imminent alarms retain their existing guards. USB charging does not auto-enter deep sleep.

Network setup closes and turns the display off after 60 seconds without touch. Locking while setup is open also closes it, allowing normal power handling on subsequent loops. Low-battery brightness limiting applies on the first boot frame. The resting character moves down 6 pixels; caption, live transcript and recording/thinking layouts keep the existing position.

Recovery: private app0 readback matched the previously built firmware byte-for-byte before the app-only flash; the original full-flash recovery and partition table were verified by the existing flasher. No Wi-Fi credentials or pairing NVS were erased.

Validation: pairing/recovery policy regressions, power-delay boundary tests, firmware build and signed iOS Release build. Hardware checks cover RX idle suspension/resumption, a speaker-to-microphone tone, manual lock and CPU throttling, automatic display timeout and network-setup timeout. Battery runtime/current is not measured by these tests: the device was USB-powered and charging at 5% when diagnosis began. A full-charge discharge run is still needed before quoting hours or percentage savings. iPhone recovery-sheet interaction remains a physical acceptance check.

Driver reference: [Espressif I2S channel lifecycle](https://docs.espressif.com/projects/esp-idf/en/release-v5.4/esp32s3/api-reference/peripherals/i2s.html).
