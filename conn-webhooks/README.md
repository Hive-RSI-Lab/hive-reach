# conn-webhooks

Receives webhooks on `127.0.0.1` only and posts each one to a thread you chose, as labelled, untrusted data under the name `conn-webhooks`. It starts no agent unless your config names one. It is not published anywhere, so nothing outside this machine can reach it until you decide otherwise. There is no Cloudflare Function or KV, and no catch-all path.

## Setup
1. Write `~/.config/h2/conn/webhooks.json`, for example:
   `{"port": 8795, "services": {"github": {"kind": "github", "thread": "my-repo"}}}`
   Per service: `kind` is `github`, `stripe`, `generic` or `telnyx`; `thread` is required; optional `agent`, `rate_per_min` (default 30), `tolerance` (seconds, default 300). Top level: optional `body_max` (bytes, default 64 KB).
2. With the dashboard's lock, save each service's secret as `conn-webhooks-<service>`. For `telnyx` that's the sender's base64 public key. Make a new one: never reuse `~/.config/h2/secrets/telnyx-*`.
3. Start it yourself, it isn't enabled: `ln -s ~/modules/conn-webhooks/h2-conn-webhooks.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user start h2-conn-webhooks`

`conn on webhooks` refuses on purpose: this is a listening port, not a connector that connects outwards.

## Publishing
Publishing it is your word, per hostname, through rootwarden. There is no blanket approval: each hostname and each service is its own decision, and no agent makes it for you. This module never publishes anything and refuses any bind but `127.0.0.1`.

This is not a route to `/sms/in`, which is limit 5 and needs your own decision.

## What each request has to pass
- The route is exactly `/hook/<service>`. Anything else is 404.
- A service with no secret refuses everything (403).
- Signatures: GitHub `X-Hub-Signature-256`; Stripe `Stripe-Signature`, with timestamp tolerance; generic `X-Webhook-Timestamp` and `X-Webhook-Signature: sha256=<hex>` over `<timestamp>.<body>`, with tolerance; Telnyx-style `Telnyx-Signature-Ed25519` and `Telnyx-Timestamp`, which refuses everything if the `cryptography` package isn't on the system Python.
- Body size cap (413), a rate cap per service (429), and no delivery twice (409), remembered across restarts.

## What it can't do
- It sends nothing out and answers senders with a status only.
- GitHub signs no timestamp, so its deliveries are remembered for 30 days, and an identical body sent again in that time is dropped, including a manual redelivery. Stripe, generic and Telnyx are remembered for twice the tolerance plus a minute.
- Local processes can use up a service's attempt window with unsigned noise, which delays real deliveries until the minute passes. They can't get anything posted.
- With `agent` set, each delivery starts that agent on outside text. Leave it out unless you want that.
