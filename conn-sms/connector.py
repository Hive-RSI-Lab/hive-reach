"""SMS through Telnyx, send only, built switched off (warden, 1105012730b5). The only recipient is the person's own number, set by them in
config; the daily cap is kept in a file. Inbound is not part of this connector: see inbound.py (not registered anywhere)."""
import datetime as dt, json, sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

API = "https://api.telnyx.com/v2"
DAILY_CAP = 20
_cap_lock = threading.Lock()


def send_sms(key, sender, to, text, api=API, http=C.http):
    """The ONLY place the Telnyx key is used to send. Thread chat-aside-0511 proposes moving the key behind a root broker: when that lands,
    replace the body of this function with a call to the broker and nothing else in the module changes."""
    return http("POST", f"{api}/messages", {"from": sender, "to": to, "text": text}, headers={"Authorization": "Bearer " + key}, timeout=30)


def read_key(path=None):
    """The one place the key is read: ~/.config/h2/secrets/telnyx-api-key."""
    return (Path(path) if path else C.SECRETS / "telnyx-api-key").read_text().strip()


class Sms(C.Connector):
    name = "sms"; label = "SMS"; size = 1000; can_receive = False
    self_chat_only = True  # the base refuses every chat but cfg["self"], which is the person's number below

    def __init__(self, cfg=None, secret="", key_path=None, http=C.http):
        super().__init__(cfg, secret)
        self.key_path, self.http = key_path, http
        num = str(self.cfg.get("person_number") or "").strip()
        self.cfg["self"] = num   # empty means every send is refused
        if num: self.cfg["home"] = num
        self.cap_file = C.DATA / "sms" / "cap.json"

    def ready(self):
        if self.cfg.get("enabled") is not True:
            return "SMS is switched off. To turn it on, set enabled to true in the conn-sms config, after setting person_number (your own phone) and from_number (your Telnyx number)."
        for k, what in (("person_number", "your own phone number"), ("from_number", "your Telnyx number")):
            if not self.cfg.get(k): return f"missing {k} in the conn-sms config: {what}"
        try: read_key(self.key_path)
        except OSError: return "no Telnyx key: save it as telnyx-api-key with the dashboard's lock"
        return ""

    def take_slot(self):
        """Count one message against today's cap, or raise. Counted before sending: a failed try still counts, which errs on the safe side."""
        cap = int(self.cfg.get("daily_cap", DAILY_CAP)); today = dt.date.today().isoformat()
        with _cap_lock:
            try: st = json.loads(self.cap_file.read_text())
            except (OSError, ValueError): st = {}
            if st.get("day") != today: st = {"day": today, "n": 0}
            if st["n"] >= cap: raise RuntimeError(f"daily SMS cap of {cap} reached")
            st["n"] += 1
            self.cap_file.parent.mkdir(parents=True, exist_ok=True); self.cap_file.write_text(json.dumps(st))

    def send(self, chat, text, files=()):
        if self.ready(): raise PermissionError(self.ready())
        if str(chat) != self.cfg["person_number"]: raise PermissionError("this connector only ever messages the person")  # belt and braces with self_chat_only
        if files: text += "\n(a file was attached; SMS can't carry it)"
        self.take_slot()
        send_sms(read_key(self.key_path), self.cfg["from_number"], self.cfg["person_number"], text, api=self.cfg.get("api", API).rstrip("/"), http=self.http)


CONNECTOR = Sms
