# conn-xmpp

Talk to the hive over XMPP one-to-one chats, using an account on a server that already exists. Needs the `slixmpp` package (uv fetches it when the service starts). Only `type=chat` messages count, and the sender is the bare JID. Group chat messages are marked not-private and dropped, and the bot never joins a room.

Set up (your steps):
1. Make an XMPP account for the bot on a server you use.
2. `conn set xmpp jid bot@example.org` (optional: `host`, `port`, `direct_tls`).
3. Save the password as `conn-xmpp` with the dashboard's lock.
4. Message the bot from your own account to get the pairing code.

Plain-text logins are refused; the connection must be encrypted. Can't do: files, OMEMO or other end-to-end encryption (messages are readable by the server). The slixmpp part was not run against a real server; the pure parts are tested.
