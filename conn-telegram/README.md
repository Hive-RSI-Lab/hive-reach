# conn-telegram

Talk to the hive from Telegram, through a bot of yours. It long-polls Telegram, so nothing listens on this machine. Private chats only: groups are ignored, and a stranger gets a pairing code at most.

## Set up (your steps)

1. In Telegram, message @BotFather, send `/newbot` and follow its questions. It gives you a token.
2. Save the token with the dashboard's lock as `conn-telegram`. Never paste it in chat.
3. Ask an agent to run `conn on telegram`.
4. Message your bot. It answers with a code. Type `pair telegram CODE` on the dashboard, as a whole line.

## What it can't do

- Bots can't start a chat: you write first.
- Bots can't fetch files over 20 MB from Telegram. Those are named in the post rather than lost.
- Telegram bot chats aren't end-to-end encrypted, so Telegram can read them.

## Tests

`python3 -I test_telegram.py`. A fake API, plus a real call with a bad token to confirm the error shape.
