# Board-specific releases and updates

Wappai supplies software, not hardware. Purchase, shipping, taxes, warranty and hardware support are provided by the seller. Wappai is independent of Waveshare.

| Board ID | Display / touch | Release state |
| --- | --- | --- |
| `ws-s3-175c` | 466×466 round / CST9217 | 1.1.4-dev.1 development package; known connected silver unit |
| `ws-s3-175` | 466×466 round / CST9217 | No Wappai firmware approved for this separate board |
| `ws-s3-18` | 368×448 / CST820 | BSP and physical validation incomplete; distribution blocked |
| `ws-s3-216` | 480×480 / CST9220 | BSP and physical validation incomplete; distribution blocked |

The shared ESP32-S3 chip identity is insufficient to distinguish these devices. Pin assignments, panel geometry, touch commands, power rails and peripheral support differ. The 1.75C firmware must never be relabeled as firmware for the other boards. Selecting an unsupported/unknown board in the installer blocks flashing. A link from the iOS update card includes the exact board ID reported by the connected firmware; no shape/name heuristic is used for updates.

## Update discovery

The iOS app reads the public GitHub `release/firmware-catalog.json`, at most once per day while foregrounded/connected, with an explicit settings check button. Failed checks retry no sooner than ten minutes automatically; manual checks remain available. Requests do not include device identifiers, conversation content or Hub credentials. GitHub still sees ordinary HTTP metadata such as the requesting IP address. The ESP32 is not woken and performs no update polling.

Each board has its own release record. SemVer compares the **running firmware version** with `version`, not with `package_version`: the original package v1.0.0-dev.1 reports `1.0.0-dev` on the device. Only a newer valid release for the exact board triggers an in-app notice (once per board/release). The app never automatically installs firmware. The initial installation/update route is currently USB through a desktop browser. It may replace settings; the installer explains backup and erase behavior. Production OTA, signed manifests and rollback qualification are not claimed by this catalog. The older developer-only Hub OTA endpoint is not exposed by this feature.

## Release qualification

Before adding a board or replacing an advertised binary:

1. Implement and review its BSP using official schematics, not just dimensions. Build that target independently.
2. On the physical target, test display boundaries, touch, BOOT press/release, PWR lock/wake, microphone, speaker, IMU, charging/battery reporting and current consumption while idle/asleep.
3. Test fresh install, Wi-Fi/BLE pairing, Hebrew conversation, reboot recovery and upgrade from the previous supported release while preserving required settings.
4. Test interrupted download/write, low-battery behavior and recovery. For OTA releases also qualify both slots, image authentication and rollback on failed startup.
5. Record board revision, source commit, toolchain, artifact hashes, date and actual evidence. Passing a build or simulator test alone is not hardware qualification. No guarantee of zero defects is implied.
6. Run `python3 tools/validate_firmware_catalog.py` and the browser/Swift policy tests. Publish separate immutable release assets per board, then update the catalog and the installer together. Retain previous recovery images. Any new board requires an explicit change to the validator's supported-board gate after completing qualification.

For 1.1.4-dev, source and software checks pass; the known 1.75C received an app-only upgrade preserving its settings and character store. The separately built public image uses empty credentials. A factory-reset public onboarding run and full battery endurance are still unqualified. The 1.8 and 2.16 boards were not connected for qualification.

Official references: [1.75C](https://www.waveshare.com/esp32-s3-touch-amoled-1.75c.htm), [1.75](https://www.waveshare.com/esp32-s3-touch-amoled-1.75.htm), [1.8](https://www.waveshare.com/product/esp32-s3-touch-amoled-1.8.htm), [2.16](https://www.waveshare.com/esp32-s3-touch-amoled-2.16.htm), [ESP-IDF OTA](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html).

## Responsive presentation layouts — 2026-11-05

The landing and development simulator now share a native-resolution layout renderer: round 466×466, rectangular 368×448 and square 480×480. Controls, timer columns and six clock faces use shape-specific margins and un-stretched vector drawing. These are browser previews with illustrative data. This update does not qualify the 1.8, 2.16 or separate 1.75 BSP, power rails, peripherals or battery behavior.
