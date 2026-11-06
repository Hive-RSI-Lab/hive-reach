# conn-whatsapp

Talk to the hive from WhatsApp's **Message Yourself** chat on your own account, through a linked device (a Baileys bridge in Node).

## Read this before you scan anything

A linked device can see all of your chats, not just one. **Only the self-chat is processed**: everything else is dropped the moment it arrives, before its text or files are stored, logged or read, and attachments from other chats are never fetched. **The code will only ever message you**: sending to any other chat is refused in code. The link session is a credential (it is as good as a logged-in device), kept in a folder only you can read and never logged. Messages the connector sends to the chat come back as echoes; they are recognised and ignored so the hive does not talk to itself.

**Any agent here could read these chats.** The link session sits under the same account as every agent, and `self` is a plain config field. So any agent could in principle read your chats or message someone else in your name. The self-chat rule above only holds for code that goes through this connector. **For the test we recommend a spare number**, so that what's exposed isn't your real chats. It's your choice.

**Ban risk:** Baileys is an unofficial WhatsApp client. WhatsApp can ban a number that uses one, and does so without warning. Consider using a spare number instead of your main one.

## Set up (your steps)

1. Put your own number in `~/.config/h2/conn/whatsapp.json`: `{"self": "46701234567"}` (digits, country code, no +).
2. Run `python3 -I ~/modules/conn-whatsapp/link.py`. It asks you to confirm the warnings, runs `npm install` for `@whiskeysockets/baileys` into this folder (`node_modules` is not committed), and shows a QR code.
3. In WhatsApp: Settings, Linked devices, Link a device, scan it.
4. `conn on whatsapp`. You are trusted from the start: your own chat needs no pairing.

The session lives in `~/.config/h2/secrets/conn-whatsapp-session/` (mode 700).

## What it can't do

Groups, other chats (dropped on purpose), more than one attachment per message in, voice or reactions. The filter is in `bridge.mjs` and again in `connector.py`. Not tried against real WhatsApp: the tests use a fake bridge, plus `node --test bridge.test.mjs` on the jid filter.
