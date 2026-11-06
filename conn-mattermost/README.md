# conn-mattermost

Talk to the hive from Mattermost direct messages. Connects out to a Mattermost server that already exists (websocket for events, REST to reply); it never hosts one.

Set up (your steps):
1. Make a bot account (System Console > Integrations > Bot Accounts) or use a personal access token, and copy its token.
2. `conn set mattermost server https://chat.example.com`
3. Save the token as `conn-mattermost` with the dashboard's lock.
4. Message the bot privately to get the pairing code.

Only direct messages (channel type D) are read; the sender is the user id. Channels and group messages are ignored. Can't do: files.
