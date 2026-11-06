# conn-signal

Talk to the hive from Signal's **Note to Self**, on your own account, through a linked device (signal-cli).

## Read this before you scan anything

A linked device can see all of your chats, not just one. **Only the self-chat is processed**: everything else is dropped the moment it arrives, before its text or files are stored, logged or read, and attachments from other chats are never fetched. **The code will only ever message you**: sending to any other chat is refused in code. The link session is a credential (it is as good as a logged-in device), kept in a folder only you can read and never logged. Messages the connector sends to the chat come back as echoes; they are recognised and ignored so the hive does not talk to itself.

**Any agent here could read these chats.** The link session sits under the same account as every agent, and `self` is a plain config field. So any agent could in principle read your chats or message someone else in your name. The self-chat rule above only holds for code that goes through this connector. **For the test we recommend a spare number**, so that what's exposed isn't your real chats. It's your choice.

Signal tolerates linked devices officially, but signal-cli is an unofficial client; a dedicated spare number is the cautious choice.

## Set up (your steps)

1. Put your own number in `~/.config/h2/conn/signal.json`: `{"self": "+46701234567"}` (no spaces).
2. Run `python3 -I ~/modules/conn-signal/link.py +46701234567`. The first time, it downloads the official signal-cli release (AsamK/signal-cli on GitHub, Java build, checked against GitHub's sha256) into `~/.local/share/`. Java must be installed (it is on the tower).
3. In Signal on your phone: Settings, Linked devices, Link new device, scan the QR code it shows (or the `sgnl://` text, if there is no `qrencode`).
4. `conn on signal`. You are trusted from the start: your own chat needs no pairing.

The session lives in `~/.config/h2/secrets/conn-signal-session/` (mode 700).

## What it can't do

Groups and other people's chats (dropped on purpose). Attachments only in the Note to Self. Not yet tried against a real signal-cli: the tests use a fake script that speaks the same JSON-RPC.
