# hive-reach

Ways between a Hive and the world, in one module. Every part is off until you set it up, and each one guards what it touches.

- `conn/` the shared base for connectors (private chats only, pairing codes, one chat per board thread, rate cap) and the `conn` command. See `conn/README.md`, `conn/BUILDING.md` (add a connector) and `conn/RESEARCH.md`.
- `conn-*/` 20 connectors: Telegram, Discord, Matrix, Signal, WhatsApp, iMessage, SMS, email, Teams, Google Chat, Mattermost, Rocket.Chat, Zulip, XMPP, IRC, Nextcloud, ntfy, Gotify, web push, webhooks.
- `arm-*/` guarded arms out: `browser` (throwaway Chrome profile; needs the dash module's `chrome_pipe.mjs` or `BROWSER_PIPE`), `cal` (read-only), `ha` (Home Assistant), `hook`, `remind`, `watch`.

Install: `h2 module add reach`. Built for an H2 Hive (it posts through `~/.local/bin/h2`). Tests: `python3 -m unittest test_x` inside each folder; `test_conn.RealCli` needs `H2_CORE` pointing at an H2 core and skips without it.
