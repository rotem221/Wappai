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

Download and unzip `Wappai-1.75C-firmware.zip` from Releases. Install `esptool` and `pyserial` in a Python virtual environment, then run:

```sh
python -m pip install 'esptool>=4.8,<6' pyserial
python flash.py --port /dev/cu.usbmodemYOUR_PORT --board 1.75C
python configure_hub.py --port /dev/cu.usbmodemYOUR_PORT
```

On Windows use a port such as `COM5`; on Linux `/dev/ttyACM0`. The flash helper verifies package hashes and saves a complete **private** device backup before writing the bootloader, partition table, OTA metadata and application. It does not erase the whole chip. If you already use another layout, inspect and retain your backup before proceeding. The merged factory image is also supplied for tools that accept a single binary at `0x0`; it is intended for initial installation and may overwrite saved settings in its address range.

`configure_hub.py` prompts for your `wss://YOUR_HOST/ws` address and the same Hub `DEVICE_TOKEN`, without showing the secret or putting it in shell history. It stores these on the device and reboots. Wi-Fi is configured through Bluetooth in the iOS app (physical BOOT confirmation), or by `tools/setup_wifi.py`. ESP32-S3 supports **2.4 GHz Wi-Fi**, not 5 GHz.

To build your own firmware, run `pio run -d firmware`. The public `secrets.example.h` is used when no ignored `secrets.h` exists. Device configuration can still be supplied after flashing.

## 3. Install the iOS development app

The release `.ipa` is **unsigned**. It cannot install directly from a Safari download. Sign it with your own provisioning/signing setup, or build from Xcode:

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
