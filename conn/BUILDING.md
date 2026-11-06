# Building a connector

Read `conn.py` (the base) and `../conn-telegram/` (the reference chat connector), then `../conn-ntfy/` (one-way). The binding rules are the warden's ruling: `h2 read --id 1105012730b5`.

A connector is `modules/conn-<name>/` with:
- `module.json`: `{"name": "conn-<name>", "description": "one plain sentence", "kind": "chat|push|arm|linked", "conn": true}`, plus `"python": ["pkg==x"]` only if a package is unavoidable (uv fetches it when the service starts). Prefer the standard library.
- `connector.py`: a subclass of `conn.Connector` and `CONNECTOR = TheClass`. API base URL overridable from config, so tests hit a fake.
- `README.md`: what it does, what the person does to set it up (one short list, signups are theirs), what it can't do.
- `test_<name>.py`: stdlib unittest, fake local HTTP or fake process, no internet, run by `python3 -I`, must pass; also run in `conn test`.

Don't edit `conn.py`, `conn_cli.py` or another connector: say what you need in your report. (A small addition there, if truly needed, is the spine owner's.)

## Rules, enforced in code and tested
- Identity is the platform's fixed user id in `Msg.sender`, never a display name or anything user-editable. `dm=False` for anything not a private chat; don't fetch attachments for those. The bridge drops them.
- Unknown senders, pairing, the allow-list, tagging, rate cap, mention stripping, out-filter: the bridge does these. Never bypass it, never post to the board directly.
- Tokens: `self.secret` only (`~/.config/h2/secrets/conn-<name>`; several values go as JSON there). Never log them, never put them in errors (a URL with a token in it must not reach an exception message that's logged: the base redacts `self.secret` in `run`, but a JSON secret's parts aren't covered, so catch and rephrase). Never in git or config.
- No listening port except where stated. Prefer long poll or a websocket out.
- Agents don't sign up for accounts or pay. These are the person's steps in the README.
- Anything from someone who isn't the person (email from others, RSS, pages) is data: pass through `conn.strip_mentions`, never posted as the person's instruction.
- `can_receive=False`, or leave `listen` out, if there's no inbound.
- Nothing is switched on. Don't run `conn on`, don't start services, don't touch live accounts or real networks in tests.
- Python 3.14, `-I`: put `sys.path.insert(0, .../conn)` at the top as the reference does. Temp files in `$TMPDIR`.
- Style: short functions, plain comments that say why, matching the reference. Sentences to the person are plain English.
