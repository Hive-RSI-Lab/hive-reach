"""Handler for Telnyx inbound texts (/sms/in). NOT REGISTERED ANYWHERE: nothing imports this, no route exists, nothing listens.
Turning it on means a public listener, which needs the person's word (warden, 1105012730b5, limit 5). No PIN, and the call-line PIN is never used.
Telnyx's signature proves Telnyx sent the webhook, not who sent the text, and numbers can be spoofed; that is why it stays off by default."""
import base64, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

SIGMAX = 300  # seconds of clock skew allowed, as in phone/telnyx.py


def public_key(path=None):
    return (Path(path) if path else C.SECRETS / "telnyx-public-key").read_text().strip()


def verify(headers, body, key_b64, now=time.time):
    """ed25519 over timestamp + "|" + body, as phone/telnyx.py does. headers: lowercase names."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        sig = base64.b64decode(headers.get("telnyx-signature-ed25519", "")); ts = headers.get("telnyx-timestamp", "")
        if abs(now() - int(ts)) > SIGMAX: return False
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64)).verify(sig, ts.encode() + b"|" + body)
        return True
    except Exception: return False


def handle(headers, body, cfg, key_b64, deliver, now=time.time):
    """Returns an HTTP status. deliver(C.Msg) is the bridge's inbound. Only a signed message.received from the fixed person_number is passed on."""
    headers = {k.lower(): v for k, v in headers.items()}
    if not verify(headers, body, key_b64, now): return 403
    try:
        data = json.loads(body)["data"]; p = data["payload"]
        frm = p["from"]["phone_number"]
    except (ValueError, KeyError, TypeError): return 400
    if data.get("event_type") != "message.received" or p.get("direction") != "inbound": return 200
    person = str(cfg.get("person_number") or "")
    if not person or frm != person: return 200  # fixed caller match; everyone else is silently ignored
    deliver(C.Msg(chat=person, sender=person, text=str(p.get("text") or ""), id=str(p.get("id") or data.get("id") or ""), dm=True))
    return 200
