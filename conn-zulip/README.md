# conn-zulip

Talk to the hive from Zulip private messages. Long polls a Zulip server that already exists; it never hosts one.

Set up (your steps):
1. In Zulip, make a generic bot and note its email and API key.
2. `conn set zulip server https://yourorg.zulipchat.com`, `conn set zulip email bot-bot@yourorg.zulipchat.com`
3. Save the API key as `conn-zulip` with the dashboard's lock.
4. Send the bot a private message to get the pairing code.

Only one-to-one private messages count; the sender is the numeric user id. Streams and group private messages are ignored. Can't do: files.
