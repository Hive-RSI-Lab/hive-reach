# conn-matrix

Talk to the hive from Matrix. It signs in as a bot account of yours on a Matrix server that already exists, and long-polls `/sync`, so nothing listens on this machine. Only a private chat counts: a room with exactly two joined members, you and the bot. This connector doesn't host a server.

## Set up (your steps)

1. Make an account for the bot on a homeserver (your own, or one you use). Don't use your own account.
2. Get an access token for that account (in Element: Settings, Help & About, Access Token, while signed in as the bot). Give it to the hive with the dashboard's lock as the secret `conn-matrix`. Never paste it in chat.
3. Put the server address in `~/.config/h2/conn/matrix.json`, for example `{"server": "https://matrix.example.org"}`.
4. From your own account, start a direct chat with the bot, with encryption turned off. The bot joins invites that are marked as direct chats.
5. Say something. It answers with a pairing code. Enter that code on the dashboard to approve it.

## What it can't do

- **Encrypted rooms are not supported.** The room must be unencrypted. If an encrypted message arrives in a two-person room, the bot answers once, in plain text, that it can't read it.
- Rooms with more than two joined members (or where the sender isn't in the room) are ignored, and no files are fetched from them.
- It joins only invites flagged as direct chats. Anyone can flag one, so a stranger can get the bot into a room, but still gets nothing past a pairing code. The bot does not leave rooms nobody pairs from; clean those up from the bot account.
- Messages sent while the connector was off are read when it comes back (it keeps its place in `~/.local/state/conn/matrix/since`), except on the very first start, when old history is skipped.
- Notices (other bots), edits, reactions, threads and emotes are ignored. Attachments you send are fetched (up to 25 MB); files the hive sends go as uploads.
- Replies are plain text. Long ones are split by the bridge at 16,000 characters.
