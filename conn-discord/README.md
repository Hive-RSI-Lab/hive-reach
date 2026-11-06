# conn-discord

Talk to the hive from Discord. It is a bot of yours: the connector opens one outbound websocket to Discord's gateway (no port is opened) and replies through Discord's web API. Only direct messages count. Anything said in a server channel is ignored, and the bot only asks Discord for DMs.

## Set up (your steps)

1. Go to https://discord.com/developers/applications and make a new application, then add a Bot to it.
2. On the Bot page, copy the token (Reset Token if you need a new one). Give it to the hive with the dashboard's lock as the secret `conn-discord`. Never paste it in chat.
3. Install the bot so you can reach it: on the Installation page add it to your user account, or build an invite link (OAuth2, scope `bot`) and add it to a server you are on. You can't DM a bot you share no server with.
4. Send the bot a direct message. It answers with a pairing code. Enter that code on the dashboard to approve it.

You do not need to turn on the Message Content intent: direct messages come with their text without it.

## What it can't do

- Server and group messages: dropped on purpose.
- Other bots and webhooks are ignored.
- Long replies are split by the bridge at 1900 characters (Discord's limit is 2000).
- Attachments you send are fetched (up to 25 MB); files the hive sends back go as an upload.
- No voice, reactions, threads or buttons. Edits to a message aren't seen.
- Mentions in replies never ping anyone.
- If the gateway link drops it reconnects and resumes the session; a missed heartbeat reply is treated as a dead link.

Config (optional, in `~/.config/h2/conn/discord.json`): `api` and `gateway` override the Discord addresses, which is how the tests use a fake.
