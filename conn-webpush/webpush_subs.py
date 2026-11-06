"""Which browsers asked for Web Push. Standard library only: dash.py loads this file too, and the dashboard never touches the private key."""
import base64, binascii, fcntl, json, os, re, tempfile, time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

MAX_SUBS = 20       # oldest goes first: enough for a person's devices, and a stuck page can't grow the file
MAX_ENDPOINT = 2048
# The server posts to whatever address a browser gave it, so only real push services are accepted: nothing here can be aimed at this machine.
HOSTS = {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}
SUFFIXES = (".push.apple.com", ".notify.windows.com")


def state_dir(home): return Path(home) / ".local/state/conn/webpush"
def config_file(home): return Path(home) / ".config/h2/conn/webpush.json"


def unb64(s):
    """Bytes from unpadded base64url, or ValueError. The decoder alone skips characters it doesn't know, so check first."""
    if not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", s): raise ValueError("not base64url")
    s = s.rstrip("=")
    try: return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except binascii.Error as e: raise ValueError("not base64url") from e


def key_ok(s, size, first=None):
    try: raw = unb64(s)
    except ValueError: return False
    return len(raw) == size and (first is None or raw[0] == first)


def endpoint_ok(url, allow=()):
    """A known push service over https on its normal port. `allow` is exact origins from the connector's own config, for a local test endpoint."""
    if not isinstance(url, str) or len(url) > MAX_ENDPOINT or re.search(r"[\s\\\x00-\x1f\x7f]", url): return False
    try: u = urlsplit(url); port = u.port
    except ValueError: return False
    if "@" in u.netloc: return False
    if f"{u.scheme}://{u.netloc}".lower() in allow: return True
    host = (u.hostname or "").lower()
    return u.scheme == "https" and port in (None, 443) and (host in HOSTS or host.endswith(SUFFIXES))


class Store:
    """A private JSON file. The dashboard adds and the connector removes, from separate processes, so every change holds a lock."""
    def __init__(self, folder):
        self.dir = Path(folder); self.file = self.dir / "subscriptions.json"

    def load(self):
        try: subs = json.loads(self.file.read_text())
        except (OSError, ValueError): return []
        return subs if isinstance(subs, list) else []

    @contextmanager
    def _locked(self):
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(self.dir, 0o700)
        fd = os.open(self.dir / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX); yield
        finally: os.close(fd)

    def _save(self, subs):
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".subs")  # mkstemp makes it 600, and the replace is whole or not at all
        try:
            with os.fdopen(fd, "w") as f: json.dump(subs, f)
            os.replace(tmp, self.file)
        except BaseException:
            Path(tmp).unlink(missing_ok=True); raise

    def add(self, sub):
        with self._locked():
            kept = [s for s in self.load() if s.get("endpoint") != sub["endpoint"]]
            self._save((kept + [sub])[-MAX_SUBS:])

    def remove(self, endpoint):
        with self._locked():
            subs = self.load(); kept = [s for s in subs if s.get("endpoint") != endpoint]
            if len(kept) != len(subs): self._save(kept)


def public_key(home):
    try: k = json.loads(config_file(home).read_text()).get("public_key")
    except (OSError, ValueError, AttributeError): return ""
    return k if key_ok(k, 65, 4) else ""


def view(home):
    k = public_key(home)
    return {"available": bool(k), "public_key": k, "count": len(Store(state_dir(home)).load())}


def clean(sub, link="", allow=()):
    """The one shape we keep, from what a browser sent, or ValueError."""
    if not isinstance(sub, dict) or not isinstance(sub.get("keys"), dict): raise ValueError("that isn't a push subscription")
    keys = sub["keys"]
    if not endpoint_ok(sub.get("endpoint"), allow): raise ValueError("this browser's push service isn't one this app knows")
    if not key_ok(keys.get("p256dh"), 65, 4) or not key_ok(keys.get("auth"), 16): raise ValueError("that isn't a push subscription")
    return {"endpoint": sub["endpoint"], "p256dh": keys["p256dh"], "auth": keys["auth"], "link": link, "at": int(time.time())}


def act(home, d, link=""):
    """What POST /api/webpush does. `link` is the address the person is using, so a click comes back to the same place."""
    store = Store(state_dir(home)); what = d.get("do")
    if what == "subscribe":
        if not public_key(home): raise ValueError("push isn't set up here yet")
        store.add(clean(d.get("subscription"), link))
    elif what == "unsubscribe":
        if not isinstance(d.get("endpoint"), str): raise ValueError("which browser?")
        store.remove(d["endpoint"])
    else: raise ValueError("subscribe or unsubscribe")
    return view(home)
