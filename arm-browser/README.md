# arm-browser

An agent-driven browser: open a page, click, type, read. `~/modules/web/web.mjs` only searches, fetches and takes screenshots (no click or type), so this is a small wrapper over the same `chrome_pipe.mjs` (debug pipe, no port opens). It needs the dash module installed (`~/modules/dash/web/test/chrome_pipe.mjs`), or `BROWSER_PIPE` set to that file; without it `browser run` fails before Chrome starts.

    browser run URL [--steps FILE|-] [--max N]

Steps are a JSON list: `{"op":"click","selector":"css"}`, `{"op":"type","selector":"css","text":"..."}`, `{"op":"wait","ms":500}`, `{"op":"text"}`. Anything else is refused.

## Guards

- Always a throwaway profile: a fresh `browser-*` dir in the temp dir, deleted afterwards.
- `--user-data-dir` is accepted only if it is already a real, empty, own-user `browser-*` directory directly in the temp dir (no symlinks). Your home, your real Chrome profile or any used dir is refused before Chrome starts. Tested.
- No other Chrome flag passes through. Only http(s) URLs, and only public ones: a literal loopback, private, link-local or unspecified address (v4 or v6, the mapped, NAT64 and 6to4 forms included), a local name (localhost, .local, .lan, .internal, .home.arpa, a bare one-word name) or a name that resolves to a local address is refused before Chrome starts. Tested.
- Page text comes back quoted, labelled "untrusted data", with mentions stripped. Sign-ins do not exist here: never type passwords or secrets, and the person does any signing up.
- Not built: the check covers only the address you give. A page can still redirect, or load images and scripts, from a local address, and Chrome resolves the name again itself (so DNS rebinding is not stopped). arm-watch pins the address; this arm does not, so keep it off machines whose local pages matter.

Tests: `python3 -I test_browser.py` (needs node; a fake Chrome records its argv, and where dash is not installed `fake_chrome_pipe.mjs` starts it, so no real Chrome was driven, and the click/type path is untested against a real page).
