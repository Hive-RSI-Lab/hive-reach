# conn-sms

Text the person's own phone through Telnyx. **Send only, and built switched off.**

## What it does
- `send` goes through one function, `send_sms`, at the top of `connector.py`. The Telnyx key (`~/.config/h2/secrets/telnyx-api-key`) is read in one function, `read_key`, and used only there. Thread chat-aside-0511 may move the key behind a root broker; `send_sms` is the only thing to change then.
- The only recipient is `person_number` from config, which only the person sets. No number is in git. Any other destination is refused in code (`self_chat_only = True`, and a second check in `send`).
- All of this holds only for code going through this connector. The config and the Telnyx key sit under the same account as every agent, so an agent could change `person_number` or use the key directly, and that spends money. See the known gap in `conn/README.md`.
- A daily cap, default 20 (`daily_cap`), kept in `~/.local/state/conn/sms/cap.json`. Failed tries count.
- Off unless config `enabled` is `true`. `ready()` says in a sentence what is missing.

## Setup (the person's steps)
1. Telnyx account, a number, and messaging registration are yours to sign up for and pay for.
2. Save the API key as `telnyx-api-key` with the dashboard's lock.
3. Config (`~/.config/h2/conn/sms.json`): `person_number` (your phone, E.164), `from_number` (your Telnyx number), then `"enabled": true`.
4. `conn on sms`.

## Inbound is NOT on
`inbound.py` has the `/sms/in` handler (ed25519 signature check as in `phone/telnyx.py`, a fixed match on `person_number`, no PIN). **The route is not registered anywhere and nothing listens.** Turning it on is a public listener, a new way in with weaker checks than the call line (a valid signature proves Telnyx sent it, not who texted; numbers can be spoofed), and **needs the person's word**. Do not reuse the call-line PIN.

## Can't do
Receive texts (until the above), send files or pictures, text anyone but the person. Sending has been tested only against a fake; Telnyx has not been called.
