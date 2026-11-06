# arm-hook

Send a short message to a web address (a webhook) that the person has approved. Command: `hook` (linked by `h2 module add arm-hook`).

## Setup (the person's steps)
1. Add a destination: `hook add NAME https://example.com/their/webhook`. An agent can only do this by pointing at the person's own post that contains the address: `hook add NAME URL --post POSTID`.
2. Optional signing: `hook add NAME URL --sign`, and save a key in the dashboard's secret box as `arm-hook-NAME`. Each request then carries `X-H2-Timestamp` and `X-H2-Signature: sha256=HMAC(key, timestamp + "." + body)`.

## Use
`hook send NAME "text"` (or `-` to read stdin), `hook list`, `hook rm NAME`. The body is `{"text": ..., "from": "h2"}`, at most 4000 characters.

## Rules, in code and tested
- Only names in `~/.config/h2/hooks.json` (written by `hook add`). http(s) only, no name or password in the address.
- Text is refused if it holds any value from `~/.config/h2/secrets` (whole file, each line, each string in a JSON file; 8+ characters), or looks like a key (sk-, xox, ghp_, AKIA, private key, JWT). The error never says which.
- Redirects are not followed; a 3xx is an error.
- Errors never print the address (it may carry a token).

## Can't do
No replies are read, no inbound. It doesn't check that a destination is safe: that's the person's call when they add it. The warden's ruling: post 1105012730b5 (outgoing webhooks: only destinations the person sets, never secrets).

Tests: `python3 -I test_hook.py` (fake local server, no internet).
