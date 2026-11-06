# conn-ntfy

Push to your phone through ntfy. One way only.

On the public server (ntfy.sh) anyone who knows a topic can read it or publish to it, so each push there says only "H2 has a message for you." and links to the dashboard. The words are dropped inside `send`. Nothing is read back from the topic.

## Set up (your steps)

1. Install the ntfy app on your phone.
2. Ask an agent to run `conn on ntfy`. It makes a random topic and prints its address. Subscribe to that in the app.
3. `conn send ntfy hello` should make your phone buzz.

With a server of your own: `conn set ntfy server https://ntfy.example.com`, and save an access token as `conn-ntfy` with the dashboard's lock. Only then do the actual words go out. It still doesn't read anything back.

## Tests

`python3 -I test_ntfy.py`. Fakes, plus one real send of the contentless line to a throwaway topic by hand on 2026-11-05.
