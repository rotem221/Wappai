# Start with Wappai

Wappai is an independent development project: a physical ESP32 companion, a personal Hub, native iOS app and Web chat. The public release contains **no shared service, account, Wi-Fi password or device credential**. You run your own Hub.

## Supported release

**Waveshare ESP32-S3-Touch-AMOLED-1.75C**, round silver enclosure, 466×466, ESP32-S3, 32 MB physical flash and 8 MB PSRAM. Firmware uses a 16 MB partition map. Do not flash this image onto the bare 1.75, rectangular 1.8, or square 2.16: their board support is not validated. The landing page shows presentation models for the future variants, not available firmware releases.

## 1. Start your Hub

Use Python 3.11+ and FFmpeg. On a Debian/Ubuntu machine install `python3-venv` and `ffmpeg` first. From the repository run:

```sh
bash server/deploy/install.sh
```

Edit `server/.env`. The installer generates a unique `DEVICE_TOKEN`; keep it private. Set `PUBLIC_URL` to your own **HTTPS** endpoint. Put the Hub behind a TLS reverse proxy or your own secure tunnel. Do not point devices at someone else's Hub.

Sign in to Claude Code on that machine, or install and sign in to Codex on the Hub. For a Mac-hosted Codex bridge, see the optional setup below. The default brain expects the Claude CLI in `~/.local/bin/claude`; set `CLAUDE_BIN` if installed elsewhere. Use only the tools/integrations you intend to expose to your assistant. Optional Home Assistant and ElevenLabs credentials belong in the Hub environment/settings, never in the app or public repository.

```sh
cd server
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8770 --no-access-log
```

The first speech-model startup downloads the Hebrew Whisper model and needs disk space, RAM and internet access. `STT_ENGINE=whisper` works without a manually installed Zipformer model; for lower-latency partial captions, install a compatible Hebrew Zipformer model and set `STREAM_MODEL_DIR` with `STT_ENGINE=hybrid`. A streaming transcription model is required for live partial speech captions. See the model's upstream license before redistributing weights.

Create a one-time pairing code on your Hub (from the server directory):

```sh
.venv/bin/python -c 'from app import admin; print(admin.new_code(pair=True))'
```

Enter your HTTPS Hub URL and that code in Wappai on iOS, or enter the code on your Hub's Web page. The code expires after five minutes and is single-use. To open advanced administration, generate a login link code with `admin.new_code()` and use `/admin/login?code=YOUR_CODE` on your own Hub.

## 2. Flash the 1.75C

The recommended public installation entry is [Wappai browser installer](https://wappai-companion.rotem221.chatgpt.site/flash.html). Use Chrome or Edge on a desktop computer and a USB **data** cable. iPhone/Safari does not provide this installation flow. Only the **1.75C in the silver enclosure** is supported; ESP Web Tools checks the chip family, not the display or enclosure.

### Back up before replacing existing software

The browser installer does **not** make a device backup. Its factory image writes from address `0x0` and may overwrite settings inside its address range even when a full-chip erase is not selected. To retain your current installation, first save a private full-chip backup with esptool in a Python virtual environment:

```sh
python -m pip install 'esptool>=4.8,<6' pyserial
python -m esptool --chip esp32s3 --port /dev/cu.usbmodemYOUR_PORT read_flash 0 ALL wappai-private-backup.bin
```

Use a new backup filename each time. On Windows use a port such as `COM5`; on Linux `/dev/ttyACM0`. Keep backups private: they can contain network credentials or device tokens. Close serial monitors before using the browser. For a device that does not appear, hold BOOT while connecting USB, release, and select the new port.

### Install in the browser

1. Open the installer. It downloads the public factory image and checks its byte length, ESP32-S3 header and pinned SHA-256 checksum before enabling installation.
2. Confirm that your hardware is the supported 1.75C and your required data is backed up.
3. Click the connect/install button and select the USB port. ESP Web Tools shows the connection, erase choice, final installation confirmation and progress in English. Selecting a port alone does not flash firmware.
4. Wait for completion, restart the device, then configure your own Hub and Wi-Fi as described below. There are no shared credentials in this image.

The browser uses the exact bytes already verified, via an in-memory Blob. It does not upload device flash or serial logs to the site. The factory binary is the same verified public `v1.0.0-dev.1` release. The previous ZIP and command-line flash helper remain available in GitHub Releases for developers; the helper creates a backup before flashing individual parts.

### Configure your Hub after flashing

The current firmware does not implement Improv Wi-Fi and the browser installer cannot provision your Hub. Obtain `configure_hub.py` from `tools/` in the source repository (or the developer package), then run:

```sh
python configure_hub.py --port /dev/cu.usbmodemYOUR_PORT
```

`configure_hub.py` prompts for your `wss://YOUR_HOST/ws` address and the same Hub `DEVICE_TOKEN`, without showing the secret or putting it in shell history. It stores these on the device and reboots. Wi-Fi is configured through Bluetooth in the iOS app (physical BOOT confirmation), or by `tools/setup_wifi.py`. ESP32-S3 supports **2.4 GHz Wi-Fi**, not 5 GHz.

To build your own firmware, run `pio run -d firmware`. The public `secrets.example.h` is used when no ignored `secrets.h` exists. Device configuration can still be supplied after flashing.

## 3. iOS App Store and developer builds

App Store distribution is planned. The website displays “Coming soon” until a real listing URL is configured; there is no public App Store link yet. You can use the personal Hub Web UI meanwhile.

For developers, the release `.ipa` is **unsigned**. It cannot install directly from a Safari download. Sign it with your own provisioning/signing setup, or build from Xcode:

1. Open `ios/Piko/Piko.xcodeproj` in Xcode with an iOS 18+ SDK.
2. Choose your own development team and a bundle identifier available to you.
3. Connect your iPhone, enable Developer Mode when prompted, and build/run the `Piko` scheme. The installed app is named **Wappai**.
4. Enter your Hub URL and pairing code; pair the nearby device and choose your 2.4 GHz network.

The development package contains no signing identity, provisioning profile or registered device identifiers. Public App Store/TestFlight distribution is planned; no public listing or invitation is claimed. Apple distribution details: https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices

## Use

Hold BOOT to speak, release to finish. PWR locks the screen until the next press. Choose Pip, Nori or Orbit; create additional characters through an approved preview before full generation. Shake reactions, character sounds, live captions and reduced motion are optional in settings. Weather and home-control requests have separate visual responses. The iOS and Web clients share conversations through your Hub.

## Verification

```sh
python -m pip install -r requirements-dev.txt
PYTHONPATH=server python -m pytest server/tests -q
pio run -d firmware
```

The originating project passed server tests, iOS simulator UI tests, desktop/mobile Web tests and physical 1.75C operation. This public package is separately rebuilt without credentials and signing. No new factory-reset onboarding or battery-endurance certification is implied. The 1.8/2.16 firmware, App Store listing, signed OTA rollback and a hosted multi-user service are not part of this release.

## Optional Codex bridge on your Mac

If Codex runs directly on the Hub, no bridge is needed for text conversations. Image generation uses the authenticated bridge. On a Mac with Codex signed in, install `fastapi` and `uvicorn` into a virtual environment, then run `tools/wappai/install_codex_bridge.py --python /absolute/path/to/venv/bin/python`. It creates a local launch agent bound only to `127.0.0.1:18773`; it does not modify any remote machine. `--prepare-only` writes the configuration without starting it.

Set `WAPPAI_CODEX_BRIDGE_TOKEN` in the Hub's private environment to the content of `~/.local/share/wappai/bridge/token` on the Mac. For a remote Hub, maintain your own SSH reverse tunnel:

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -R 127.0.0.1:18773:127.0.0.1:18773 YOUR_SSH_HOST
```

Keep both ends bound to loopback. Restart the Hub after configuring its environment. Never put this token in Git, a browser URL or a command-line argument. The text adapter was tested against Codex app-server 0.164; image capability depends on the installed Codex version/account. The app reports missing capability instead of pretending an image was generated.

## Current device navigation

Swipe sideways between pages. Drag on the right screen edge to adjust brightness, or the left edge to adjust volume; release completes the change with visual feedback (and a volume tone when sound is safe). Long-press the clock to choose one of six faces. The settings page contains Wi-Fi and screen-off; the timer has separate hours, minutes and seconds. Native and Web clients receive the applied device settings through the Hub.

The public installer version may lag the source while a new artifact is being qualified. Always follow the exact board and version in the catalog. Future onboarding work is described in [the rollout plan](END_USER_ROLLOUT.he.md).
