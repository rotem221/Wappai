# iOS distribution and App Store readiness

This is a release gate, **not a claim of Apple approval**. Do not upload a development build or declare all checks complete merely because Xcode builds it.

## Implemented

- Native SwiftUI iPhone/iPad target; iOS 18 minimum, RTL Hebrew, system/light/dark appearance, accessibility labels and native control patterns.
- App icon, display name Wappai, no ZIP/unsigned-IPA promise on the landing page.
- APNs application delegate, notification permission requested by an explicit Settings action, token registration/opt-out, sandbox vs production configuration and `aps-environment` entitlement.
- In-app links for privacy, terms and support. Explicit meeting-recording consent and visible device recording indicator. Meetings can be deleted including the configured cloud objects.
- Removed broad arbitrary-load permission from WKWebView configuration; native Hub connection requires HTTPS.
- `PrivacyInfo.xcprivacy`: no tracking, app-functionality data declarations and UserDefaults required-reason API entry. Audit the final archive/SDK manifests and App Store privacy answers together; manifest entries do not replace the App Store Connect privacy questionnaire.
- Voice/image/cloud credentials remain on the owner's Hub, not in the app bundle. App tokens are in Keychain. Debug test fixtures do not run in Release.

## Required before submission

1. **Apple account and identifiers:** active paid Developer membership, App Store Connect app record, correct bundle ID/team, Push capability enabled, production distribution profile/certificate. Current source build is not an App Store upload.
2. **Actual APNs test:** install a correctly signed build on a physical iPhone, grant/deny/revoke notifications; test timer and meeting delivery while foreground/background/terminated, token replacement, reinstall, offline return and opt-out. Simulator interface tests do not prove APNs delivery.
3. **Publisher Push service decision:** a single App Store app cannot safely distribute its `.p8` signing key to every self-hosted Hub. Run a protected publisher-owned push relay with per-owner authorization/rate limits/deletion policy, or restrict Push to developer-signed deployments until that relay exists. No public relay has been provisioned by this change. Never put publisher APNs keys in installers or GitHub.
4. **Review access:** provide a maintained review Hub/account, current pairing instructions and a physical-device video. Explain the hardware dependency and offer access to the supported 1.75C. Debug sample launch arguments are not a reviewer demo mode. Do not point reviewers to an owner's private personal Hub.
5. **Privacy and consent:** verify the published policy covers microphone recordings, transcripts, generated images, device/APNs tokens, owner-hosted storage, optional S3 and chosen AI/voice providers. Complete App Store privacy labels for the actual deployment. Do not claim data never leaves the device. Recording participants must receive appropriate notice/consent.
6. **Screenshots and metadata:** take Release screenshots on supported iPhone/iPad sizes; no private conversation, keys, beta labels or misleading unsupported-device claims. Provide support URL, category, age-rating answers and localized description.
7. **Physical devices:** test Bluetooth ownership, Wi-Fi changes, lock/hold-to-talk, actual microphone/speaker, SD only on qualified boards, notification permission and low-memory/background behavior. The user's iPhone was unavailable during this task; only simulator UI and builds were available.
8. **Build validation:** archive Release, inspect entitlements/embedded provisioning profile/privacy manifest, validate via Organizer/App Store Connect, then TestFlight internal testing. Only after all gates pass submit for review. Apple may request additional information or changes.

## Suggested review notes

Wappai is a companion for a supported Waveshare 1.75C ESP32 device and an owner-operated Hub. The app manages Bluetooth/Wi-Fi pairing, chat, character preferences and meeting recordings. The ESP32 microphone performs recording; the app requires an explicit start action and displays recording state. The Hub performs transcription and optional AI summarization. Optional cloud storage and notifications are configured separately. Hardware purchases are from independent vendors; Wappai is not affiliated with Waveshare.

Add the actual reviewer credentials and private test instructions in App Store Connect, **not in this repository**.

## Apple references

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Remote notification provider setup](https://developer.apple.com/documentation/usernotifications/setting-up-a-remote-notification-server)
- [Required-reason APIs](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype)
- [Protecting the user's privacy](https://developer.apple.com/documentation/uikit/protecting-the-user-s-privacy)
