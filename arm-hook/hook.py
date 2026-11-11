#!/usr/bin/env python3
"""hook: outgoing webhooks to destinations the person approved, listed in ~/.config/h2/hooks.json.
  hook add NAME URL [--sign] [--post ID]   (the person types it; an agent must point at the person's own post that holds the URL)
  hook send NAME TEXT (or - for stdin)     hook list     hook rm NAME
Nothing leaves that holds a value from ~/.config/h2/secrets. Redirects are never followed. --sign adds an HMAC with the key in secret arm-hook-NAME."""
import datetime as dt, hashlib, hmac, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

HOOKS = C.HOME / ".config/h2/hooks.json"
MAX_TEXT = 4000
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}$")
# Shapes of keys that are secrets whether or not they sit in the box.
SHAPES = re.compile(r"sk-[A-Za-z0-9_-]{16,}|xox[abprs]-[\w-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|eyJ[\w-]{15,}\.[\w-]{10,}\.[\w-]{5,}")


def load(path=None):
    try: return json.loads(Path(path or HOOKS).read_text())
    except (OSError, ValueError): return {}


def save(hooks, path=None):
    p = Path(path or HOOKS); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(hooks, indent=1) + "\n"); p.chmod(0o600)


def secret_values(secrets_dir=None):
    """Every value in the secret box: whole file, each line, each string inside JSON. Short ones are skipped (they'd match ordinary words)."""
    out = set()
    for f in sorted(Path(secrets_dir or C.SECRETS).glob("*")):
        try: raw = f.read_text().strip()
        except (OSError, ValueError): continue
        out |= {raw, *(l.strip() for l in raw.splitlines())}
        try: out |= set(strings(json.loads(raw)))
        except ValueError: pass
    return {v for v in out if len(v) >= 8}


def strings(x):
    if isinstance(x, str): yield x
    elif isinstance(x, dict): yield from (s for v in x.values() for s in strings(v))
    elif isinstance(x, list): yield from (s for v in x for s in strings(v))


def leaks(text, secrets_dir=None):
    """True when the text holds a secret's value or looks like a key. Says nothing about which."""
    return bool(SHAPES.search(text)) or any(v in text for v in secret_values(secrets_dir))


def check_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname: raise SystemExit("hook: the address must be http:// or https://")
    if u.username or u.password: raise SystemExit("hook: no name or password inside the address; use --sign for a key")


def person_post(pid, url, board=None):
    """An agent may add a hook only when the person's own post says so: it has to be from person and hold exactly this URL."""
    try: lines = Path(board or C.BOARD).read_text().splitlines()
    except OSError: return False
    for l in reversed(lines):
        try: p = json.loads(l)
        except ValueError: continue
        if p.get("id") == pid: return p.get("from") == "person" and url in post_urls(p.get("text", ""))
    return False


def post_urls(text):
    """The addresses written in a post, each whole. A match has to be exact: a URL that is only the start of the person's
    (https://hooks.example.co inside https://hooks.example.com/x) is a different place."""
    return {u.rstrip(".,;:!?") for u in re.findall(r"https?://[^\s<>\"'`]+", text)}


def add(name, url, sign=False, post=None, hooks_path=None, board=None, agent=None):
    if not NAME.match(name): raise SystemExit("hook: the name is lowercase letters, digits, - or _")
    check_url(url)
    if agent and not person_post(post, url, board): raise SystemExit("hook: only the person sets a destination. Use --post ID of their post that holds this address.")
    hooks = load(hooks_path); hooks[name] = {"url": url, "sign": bool(sign)}; save(hooks, hooks_path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None


def send(name, text, hooks_path=None, secrets_dir=None, timeout=15, now=None):
    hooks = load(hooks_path)
    if name not in hooks: raise SystemExit(f"hook: {name} is not in the person's list")
    if len(text) > MAX_TEXT: raise SystemExit(f"hook: too long ({len(text)}, at most {MAX_TEXT})")
    if leaks(text, secrets_dir): raise SystemExit("hook: refused. The text holds something that looks like a secret.")
    h = hooks[name]; body = json.dumps({"text": text, "from": "h2"}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "h2-hook"}
    if h.get("sign"):
        key = C.read_secret(f"arm-hook-{name}", Path(secrets_dir or C.SECRETS) / f"arm-hook-{name}")
        if not key: raise SystemExit(f"hook: {name} wants signing but there's no key in secret arm-hook-{name}")
        ts = str(int(now or dt.datetime.now().timestamp()))
        headers |= {"X-H2-Timestamp": ts, "X-H2-Signature": "sha256=" + hmac.new(key.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()}
    req = urllib.request.Request(h["url"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as r: return r.status
    except urllib.error.HTTPError as e:
        raise SystemExit(f"hook: {name} answered {e.code}" + (" (a redirect; not followed)" if 300 <= e.code < 400 else "")) from None
    except (urllib.error.URLError, OSError) as e:  # the address may hold a token, so say nothing of it
        raise SystemExit(f"hook: could not reach {name} ({type(getattr(e, 'reason', e)).__name__})") from None


def main(argv):
    if not argv or argv[0] not in ("add", "send", "list", "rm"): return print(__doc__) or 2
    cmd, a = argv[0], argv[1:]
    sign = "--sign" in a; a = [x for x in a if x != "--sign"]
    post = None
    if "--post" in a: i = a.index("--post"); post = a[i + 1] if i + 1 < len(a) else None; del a[i:i + 2]
    agent = bool(os.environ.get("H2_NAME"))  # every agent run has a name; calling yourself "person" doesn't make you the person
    if cmd == "add" and len(a) == 2: add(a[0], a[1], sign, post, agent=agent); print(f"added {a[0]}")
    elif cmd == "send" and len(a) >= 2:
        send(a[0], sys.stdin.read() if a[1:] == ["-"] else " ".join(a[1:])); print("sent")
    elif cmd == "list":
        for n, h in sorted(load().items()): print(n, urllib.parse.urlsplit(h["url"]).netloc, "signed" if h.get("sign") else "")
    elif cmd == "rm" and len(a) == 1:
        hooks = load(); hooks.pop(a[0], None); save(hooks)
    else: return print(__doc__) or 2
    return 0


if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
