# Pip gallery revisions and completion notifications — 2026-11-04

## Behavior

Pending Pips now appear in the character grid above the creation button. A generated design is labelled “תצוגה מקדימה”. Image-based creation has an optional description field again; the server preserves the supplied instructions. Reopening/editing a draft or published custom character restores its original normalized image and description. Removing a reference keeps the text and explicitly disables server reference reuse. Replacing a draft retains its Pip identity, supersedes its previous approval and displays one current card.

Preview completion and full-pack completion emit separate events. Connected iOS/Web clients show a completion notice. iOS reconciles job states on reconnect and persists stage markers to suppress repeated completion notices. Opted-in APNs devices receive deduplicated outbox entries with a gallery job reference; uploaded images/descriptions are excluded from Push payloads. Failed/cancelled generation does not announce success. The full-generation SHA approval gate and three protected built-ins remain enforced.

## Validation

- 82 server tests passed in the private and sanitized public repositories. Added coverage for original reference/description retention, superseded preview rejection, same Pip identity, explicit reference removal, protected reference access, notification completion stages, deduplication, opt-out and migration from the existing notification table.
- All 11 native simulator UI tests passed with zero failures. The tests exercise a preview card inside the grid, completion notice, restoring the reference and text, retaining the text after removing the image, and the existing image-only/text workflows. Images are deterministic fixtures; no new paid Codex generation was requested by the tests.
- The full WebKit browser suite passed against an isolated Hub: preview card placement, unchanged decoded source pixels after reopening, description persistence, revision without a duplicate card, completion notice, final approval/cancel and existing chat/settings/RTL coverage.
- Hub source, conversation database and notification database were backed up before deployment. Deployment was performed while the device was idle and no generation job was running. Existing preview/reference routes were checked after restart without modifying user jobs, Pips or conversations. The ESP32 reconnected online.
- A signed local Release build was installed on the paired iPhone. The locked phone prevented launching for physical interaction testing. Firmware was not changed; gallery polling is suspended when the app is inactive and while its creation sheet handles the active job.

## Push limitation

The live Hub reports APNs is not configured, and the cached Xcode signing profile lacks Push capability. As in the preceding update, the local installed build uses an isolated empty-entitlement copy; repository Push configuration is preserved. In-app completion notices work with the open/reconnected app. Background/terminated-app Push delivery remains unavailable until a developer account, Push-enabled signing profile and APNs backend are configured and tested. This report does not claim physical Push delivery or App Store approval.

Final screenshots were visually inspected: the completion banner is below the navigation controls, and the reference/description remain available in the edit form.
