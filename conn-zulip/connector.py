"""Zulip: long poll on /api/v1/events, private messages only; the sender is the numeric sender_id (an email can be changed). The server
already exists; this never hosts one. Warden's ruling: 1105012730b5."""
import base64, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


class Zulip(C.Connector):
    name = "zulip"; label = "Zulip"; size = 9000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.base = self.cfg.get("server", "").rstrip("/"); self.me = None

    def ready(self):
        if not self.base or not self.cfg.get("email"): return "no server or bot email: `conn set zulip server https://x.zulipchat.com` and `conn set zulip email bot@x.zulipchat.com`"
        return "" if self.secret else "no API key: save it as conn-zulip with the dashboard's lock"

    def call(self, method, path, params=None, timeout=30):
        auth = base64.b64encode(f"{self.cfg['email']}:{self.secret}".encode()).decode()
        url, body, h = f"{self.base}/api/v1{path}", None, {"Authorization": "Basic " + auth}
        if params and method == "GET": url += "?" + urllib.parse.urlencode(params)
        elif params:
            body = urllib.parse.urlencode(params).encode(); h["Content-Type"] = "application/x-www-form-urlencoded"
        r = C.http(method, url, body=body, headers=h, timeout=timeout)
        if r.get("result") == "error": raise RuntimeError(f"{path}: {r.get('msg', 'error')[:100]}")
        return r

    def send(self, chat, text, files=()):
        if text: self.call("POST", "/messages", {"type": "private", "to": f"[{int(chat)}]", "content": text})

    def handle(self, ev, inbound):
        m = ev.get("message") or {}
        if ev.get("type") != "message" or m.get("type") != "private" or not m.get("sender_id") or m["sender_id"] == self.me: return
        # a group message has more than two people in it: not a private chat with one person
        dm = len(m.get("display_recipient") or []) <= 2
        inbound(C.Msg(chat=str(m["sender_id"]), sender=str(m["sender_id"]), text=m.get("content", ""), id=str(m.get("id", "")), dm=dm,
                      name=m.get("sender_full_name", "")))

    def listen(self, inbound):
        self.me = self.call("GET", "/users/me")["user_id"]
        q = self.call("POST", "/register", {"event_types": '["message"]', "apply_markdown": "false"})
        qid, last = q["queue_id"], q["last_event_id"]
        while True:
            r = self.call("GET", "/events", {"queue_id": qid, "last_event_id": last}, timeout=120)
            for ev in r.get("events") or []:
                last = max(last, ev.get("id", last)); self.handle(ev, inbound)


CONNECTOR = Zulip
