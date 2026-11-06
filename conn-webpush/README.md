# conn-webpush

Sends a real Web Push to the browsers and phones that opted in on the dashboard, so it works with the page closed. A post addressed to the person sends each of them one fixed line, "H2 has a message for you", and a link back to the dashboard. The line never changes, whatever the post said, because push services (Google, Mozilla, Apple, Microsoft) are third parties. The payload is also encrypted to the browser (RFC 8291), and signed with this machine's VAPID key (RFC 8292).

## Setup

1. Run `conn on webpush`. It makes the keypair on this machine, saves the private half in `~/.config/h2/secrets/conn-webpush` and starts the service. Needs `cryptography` on the system Python for this step; the service itself gets it through uv.
2. Restart the dashboard once, if it has been running since before this module was added.
3. In each browser: Settings, "Push notifications", "Turn on push". The browser asks once.
4. On an iPhone or iPad, first add the dashboard to the Home Screen and open it from there. Apple offers push only to an installed page.

## What it keeps

- The private key: only in the secrets file, mode 600. The dashboard reads only the public key, from `~/.config/h2/conn/webpush.json`.
- Subscriptions: `~/.local/state/conn/webpush/subscriptions.json`, mode 600. At most 20, oldest dropped. Only a full sign-in can read the count, add one or remove one.

Running `conn on webpush` again keeps the existing key. If you delete the key, every browser has to turn push off and on again.

## What it can't do

- It can't carry the message, or anything the person types back. `can_receive` is False. They open the dashboard to read and answer.
- It can't reach a browser whose push service isn't on the list in `webpush_subs.py`: Chrome and Edge through Google or Microsoft, Firefox through Mozilla, Safari through Apple. Another browser is told so when it tries. The server posts to the address a browser gives it, so that list is what stops the address pointing anywhere else; redirects aren't followed either.
- It needs https or localhost: browsers refuse push on anything else.
- It doesn't notice a browser leaving until the push service answers 404 or 410, which then removes that subscription.
- If a browser renews its subscription on its own, the server isn't told until the next delivery fails. Turn push off and on in that browser.

Publishing needs nothing new: the dashboard's existing tunnel serves the endpoints, and there is no Cloudflare Function or KV.
