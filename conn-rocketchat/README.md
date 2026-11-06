# conn-rocketchat

Talk to the hive from Rocket.Chat direct messages. Polls (every 3 seconds, `poll` to change) the direct-message rooms of a server that already exists; it never hosts one.

Set up (your steps):
1. Make a bot user or a personal access token in Rocket.Chat and note the user id and token.
2. `conn set rocketchat server https://chat.example.com`
3. Save `{"user_id": "...", "token": "..."}` as `conn-rocketchat` with the dashboard's lock.
4. Message the bot privately to get the pairing code.

The sender is the user id. Direct rooms with more than two people are ignored. Can't do: files, channels.
