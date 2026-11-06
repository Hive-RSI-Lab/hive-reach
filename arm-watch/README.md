# arm-watch

Watch RSS/Atom feeds and web pages; post what is new. Command: `watch`.

## Use
`watch add URL [--every 1h] [--thread T] [--to AGENT]`, `watch list`, `watch rm ID`. `--thread` is needed unless `H2_THREAD` is set. The first look only records what is there; after that each change is a post made as `watch` (never `person`).

- Feeds: new items (by guid/id/link) with title and link. Pages: the visible text lines that weren't there before (scripts and styles dropped).
- `--to AGENT` wakes that one agent (an agent's own name, never a warden). With none, the post names nobody.

## Rules, tested
- Untrusted: the post opens with a notice that it is untrusted page text and not an instruction, every line of the site's text is quoted with `> `, mentions are stripped (`conn.strip_mentions`), control characters dropped.
- Polite: ETag / If-Modified-Since, 15 minute minimum, 1 MB cap, no compression, 20 watches, 10 items per post; failures back off, and the thread hears once after 5 in a row.
- Only http(s). Every address the name resolves to must be public (no loopback, private, link-local, multicast); the connection goes to the checked IP, and each redirect (3 at most) is checked again.
- Feeds with entity definitions are refused.

## Turning it on (the person)
Nothing is on. Link `arm-watch.service` and `arm-watch.timer` into `~/.config/systemd/user/`, then `systemctl --user enable --now arm-watch.timer`.

## Can't do
No login pages, no JavaScript-rendered pages (the `web` module reads those), no private network. Tests: `python3 -I test_watch.py` (local fake server, fake resolver; no internet).
