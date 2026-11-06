# conn-irc

Talk to the hive over IRC private messages. TLS only (default port 6697); there is no plain option.

Who is talking: IRC nicks can be taken by anyone, so the sender is the network account (NickServ) the server reports with each message (IRCv3 `account-tag`; `account-notify` is requested too). Someone not logged in has no identity: their message is dropped and they get no reply. Anything sent to a channel is ignored, and the bot never joins one. The server must support SASL and account-tag (Libera.Chat and OFTC-style networks with services do).

Set up (your steps):
1. Register an account for the bot with the network's services (e.g. NickServ REGISTER) and pick a nick.
2. `conn set irc server irc.example.net`, `conn set irc nick mybot` (optional: `port`, `sasl_user` if it differs from the nick, `cafile` for a private CA).
3. Save the account's password as `conn-irc` with the dashboard's lock (used for SASL PLAIN).
4. Message the bot from your own logged-in account to get the pairing code.

Can't do: files, channels, a login-less chat. Replies go to the nick that last wrote from your account since the bot started, so write first after a restart.
