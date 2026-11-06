# conn

The shared base for connectors: other apps the person can reach the hive through. `conn-*` modules each hold one app. The rules come from the warden's ruling, post `1105012730b5`. `BUILDING.md` says how to add a connector; `RESEARCH.md` says why this set.

## Use

- `conn list`: every connector, whether it runs, and what it still needs.
- `conn on NAME`, `conn off NAME`: start or stop its service (`conn@NAME`).
- `conn send NAME TEXT`: send a message to the person's paired chat, to try it.
- `conn test`: run all the connectors' test suites.
- `conn set NAME KEY VALUE`: change a config value in `~/.config/h2/conn/NAME.json`. `allow` can't be set this way, and an agent can't set `allow_from`, `self`, `person_number` or `enabled`.
- `conn who NAME`, `conn log NAME`, `conn deny NAME SENDER`.
- Tokens go through the dashboard's lock as `conn-NAME`, and land in `~/.config/h2/secrets`.

## What it enforces

- **Who counts:** the platform's fixed user id, in private chats only. Display names don't count. Group and server messages are dropped.
- **Strangers:** a pairing code at most, once an hour. No board post, no agent, no files fetched.
- **Approving:** only the person, by typing `pair NAME CODE` on the dashboard. Text arriving over a channel can't change the allow-list.
- **Marking:** each inbound post is tagged `(from LABEL)`. It is never the person's word on a hard limit or to the root warden.
- **Rate:** a cap per chat.
- **Untrusted text:** mentions are stripped from anything from outside, so it can't start an agent.

## A known gap

Agents run as the same Unix user as everything else here, and that is wider than the allow-list.

- **The list.** `conn pair`, `conn allow` and `conn set` refuse when `H2_NAME` is set. That stops text arriving over a channel from changing the list by itself. It does not stop an agent tricked by text it read: it could run the bypass (`h2 post --as person` with `H2_POST_VIA=web-pair`) with a code an outsider got from the bot, and let the outsider in. That is the realistic route, more than a rogue agent.
- **The link sessions.** WhatsApp and Signal sessions sit in `~/.config/h2/secrets` under this account, and `self` is a plain config field. Any agent could in principle read those chats or message someone else in the person's name. The self-chat rule only holds for code that goes through the connector. `person_number` on SMS has the same weakness.

What makes a bypass visible (it raises the bar, it isn't a wall, and it can be tampered with too):

- Every pairing or list change sends a line over that channel and posts in the thread, with the sender's id. `conn deny` isn't guarded but is told the same way.
- Each connector compares the live list and its config with what was paired, about every 30 s while it runs, and alerts once for each difference. `conn who` shows it too. `conn accept NAME`, from the person's own shell, says the list as it stands is right.
- A post marked `web-pair` that isn't in the dashboard's own record (`~/.local/state/conn/pair-accepted.jsonl`) is refused and alerted.

**The move (warden's ruling 1105030716fe).** Before any two-way connector stays on past 2026-11-13, or as soon as the person says keep it, whichever is first, the allow-list and the link sessions move to another account, and the connector does its send and receive from there. It is its own job, asked of the root warden, with the design written first. If it isn't done by then, the connector goes off until it is. One-way contentless ntfy and read-only connectors with no sender list don't need the move.

## Tests

`python3 -I test_conn.py`. Fake servers only.
