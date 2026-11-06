"""Web Push (RFC 8291 encryption, RFC 8292 VAPID) to the browsers that opted in on the dashboard. One way, and contentless: push services are third
parties, so every browser gets one fixed line and a link, whatever the post said."""
import base64, hashlib, hmac, json, os, struct, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import webpush_subs as S

LINE = "H2 has a message for you"
CLICK = "https://hive.example.org"
TTL = 86400       # a phone that's off for a day still hears; after that the message is old news
JWT_LIFE = 12 * 3600
TIMEOUT = 20


def b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# Imported here, not at the top: the unit's `ready` check and `conn list` run on the system Python, which may not have the package. `conn run` does, through uv.
def crypto():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return hashes, serialization, ec, utils, AESGCM


def public_bytes(key):
    _, ser, *_ = crypto()
    return key.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint)


def key_from_scalar(raw):
    ec = crypto()[2]
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def new_key():
    ec = crypto()[2]
    return ec.generate_private_key(ec.SECP256R1())


def hkdf(salt, ikm, info, size):
    """RFC 5869 for up to one block, which is all RFC 8291 asks for."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:size]


def encrypt(plain, ua_public, auth, sender=None, salt=None):
    """One aes128gcm record for one browser. sender and salt are fresh every time; they're parameters only so the RFC's example can be checked."""
    _, _, ec, _, AESGCM = crypto()
    sender = sender or new_key(); salt = salt or os.urandom(16)
    as_public = public_bytes(sender)
    shared = sender.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    ikm = hkdf(auth, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    sealed = AESGCM(cek).encrypt(nonce, plain + b"\x02", None)
    return salt + struct.pack(">IB", 4096, len(as_public)) + as_public + sealed


def vapid_token(key, endpoint, contact, now=None):
    hashes, _, ec, utils, _ = crypto()
    u = urlsplit(endpoint)
    head = b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(now or time.time()) + JWT_LIFE, "sub": contact}).encode())
    r, s = utils.decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{head}.{claims}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None  # the address was checked; a redirect would go somewhere that wasn't


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def post(url, body, headers):
    """The HTTP status. Nothing from the push service's answer is kept: the reason text can quote the endpoint."""
    try:
        with OPENER.open(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout=TIMEOUT) as r: return r.status
    except urllib.error.HTTPError as e:
        e.close(); return e.code


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".new-")  # 600 from its first moment
    try:
        with os.fdopen(fd, "w") as f: f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True); raise


class WebPush(C.Connector):
    name = "webpush"; label = "Web Push"; size = 0; can_receive = False

    def store(self): return S.Store(C.DATA / "webpush")

    def ready(self):
        if not S.key_ok(self.secret, 32): return "no key yet: `conn on webpush` makes one on this machine"
        if not S.key_ok(self.cfg.get("public_key"), 65, 4): return "no public key in the config: `conn on webpush` writes it"
        return ""

    def setup(self):
        """Make the keypair once. A key that exists stays: replacing it would silently end every browser's subscription."""
        path = C.secret_path(self.name)
        secret = self.secret or C.read_secret(self.name)
        try:
            try: key = key_from_scalar(S.unb64(secret)) if S.key_ok(secret, 32) else None
            except ValueError: key = None  # not a point on the curve: nothing could have used it
            if key is None:
                key = new_key()
                write_private(path, b64(key.private_numbers().private_value.to_bytes(32, "big")))
        except ImportError: sys.exit("conn webpush: making the key needs the Python package cryptography on the system Python")
        return {"public_key": b64(public_bytes(key)), "pings": self.cfg.get("pings", "short"), "home": "browser"}

    def click(self, sub):
        link = sub.get("link")
        return link if isinstance(link, str) and link.startswith("https://") else self.cfg.get("click") or CLICK

    def deliver(self, key, sub):
        """"ok", "gone" (the browser has left: forget it) or "failed" (worth trying again)."""
        endpoint = sub.get("endpoint")
        if not S.endpoint_ok(endpoint, tuple(self.cfg.get("allow_origins") or ())): return "gone"
        plain = json.dumps({"title": "H2", "body": LINE, "url": self.click(sub)}).encode()
        try: body = encrypt(plain, S.unb64(sub.get("p256dh")), S.unb64(sub.get("auth")))
        except (ValueError, TypeError): return "gone"  # keys no one could encrypt to
        contact = self.cfg.get("contact") or self.cfg.get("click") or CLICK
        headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(TTL), "Urgency": "high", "Topic": "h2-waiting",
                   "Authorization": f"vapid t={vapid_token(key, endpoint, contact)}, k={self.cfg['public_key']}"}
        try: status = post(endpoint, body, headers)
        except OSError: return "failed"
        return "gone" if status in (404, 410) else "ok" if 200 <= status < 300 else "failed"

    def send(self, chat, text, files=()):
        """`text` is ignored on purpose. Raises only if nobody got it, so one dead phone can't repeat the line on every other device."""
        store = self.store(); subs = store.load()
        if not subs: return
        key = key_from_scalar(S.unb64(self.secret))
        got = failed = 0
        for sub in subs:
            outcome = self.deliver(key, sub)
            if outcome == "gone": store.remove(sub.get("endpoint"))
            got += outcome == "ok"; failed += outcome == "failed"
        if failed and not got: raise RuntimeError(f"no push service took the message ({failed} tried)")


CONNECTOR = WebPush
