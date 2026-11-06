# conn-gotify

Push to your phone through Gotify. Outbound only, nothing comes back.

Gotify is self-hosted, so this needs a Gotify server of yours: it can't be used without one, and this module doesn't run one.

Set up (your steps):
1. Have a Gotify server and the Gotify app on your phone.
2. Create an application in Gotify and copy its token.
3. `conn set gotify server https://gotify.example.com`
4. Save the token as `conn-gotify` with the dashboard's lock.

Content-free by default: the push says only "H2 has a message for you." Words go out only if the server is https and you set `conn set gotify carry_words true`; over http they never do. Can't do: receiving, files.
