# conn-nextcloud

Talk to the hive from Nextcloud Talk. Polls a Nextcloud that already exists through its OCS API; it never hosts one.

Set up (your steps):
1. Make a Nextcloud user for the bot and create an app password (Settings > Security).
2. `conn set nextcloud server https://cloud.example.com`, `conn set nextcloud user botname`
3. Save the app password as `conn-nextcloud` with the dashboard's lock.
4. Start a one-to-one Talk conversation with the bot to get the pairing code.

Only one-to-one conversations (room type 1) are read, and the sender is the `actorId` of a real user (guests and bots are ignored). Group and public conversations are never fetched. Can't do: files, reactions.
