# Pip image connection recovery — 2026-11-04

The iOS photo requests reached the Hub, but an orphaned reverse SSH forward on
loopback port 18773 accepted TCP without delivering HTTP to the Mac. New tunnel
connections then failed because that port was still occupied. Local Codex image
capability was healthy. The failed jobs retained their original reference files.

The deployment now uses server-side SSH keepalives scoped to the paired Mac's
Tailscale address and tunnel user: `ClientAliveInterval 30` and
`ClientAliveCountMax 3`. This releases stale forwards after an unresponsive
connection. Validate SSH configuration with `sshd -t` before reloading; keep an
existing administrative session open. An already-orphaned connection must be
identified from the exact listening socket before terminating that connection.
Do not kill unrelated SSH sessions or expose the bridge beyond loopback.

The image pipeline now checks the authenticated bridge capability with a
15-second timeout before starting the longer generation request. Network and
generation timeouts produce distinct Hebrew messages and preserve the draft.
Requests are not silently resubmitted after a generation timeout, avoiding
duplicate quota use. Disconnected bridge requests cancel and join the worker;
the nonstandard HTTP 499 response now has an explicit detail rather than
raising ValueError in Starlette.

Validation: 29 creation/bridge tests, including preview approval, image and text
preservation, full pack compilation, protected built-in characters, completion
notifications, stale-forward preflight failure, and disconnected worker cleanup.
The deployed bridge capability succeeds through the server-to-Mac tunnel.

Live acceptance: the user's latest failed photo draft was retried through
`POST /v1/pip-jobs`, retaining its original image and description and superseding
the failed entry. It completed as `preview_ready`; its 512×512 RGBA preview and
SHA-256 match the API record. Final application awaits the user's preview approval.
No iOS binary or firmware replacement was required.
