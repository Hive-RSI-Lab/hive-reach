"""Rocket.Chat: poll the direct-message rooms (im.list, im.messages) over REST. The sender is the user id (_id), never the username.
The secret is JSON {"user_id": ..., "token": ...}. The server already exists; this never hosts one. Warden's ruling: 1105012730b5."""
import json, sys, time, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


class RocketChat(C.Connector):
    name = "rocketchat"; label = "Rocket.Chat"; size = 4000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.base = self.cfg.get("server", "").rstrip("/")
        try: self.creds = json.loads(secret) if secret else {}
        except ValueError: self.creds = {}
        self.cursor = {}  # room id -> ts of the newest message seen

    def ready(self):
        if not self.base: return "no server: `conn set rocketchat server https://chat.example.com`"
        if why := C.plain_refused(self.base, self.cfg): return why
        if not (isinstance(self.creds, dict) and self.creds.get("user_id") and self.creds.get("token")):
            return 'no login: save {"user_id": "...", "token": "..."} as conn-rocketchat with the dashboard\'s lock'
        return ""

    def call(self, method, path, params=None, body=None):
        h = {"X-User-Id": self.creds["user_id"], "X-Auth-Token": self.creds["token"]}
        url = f"{self.base}/api/v1{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
        try: r = C.http(method, url, body=body, headers=h, timeout=30)
        except Exception as e:  # the JSON secret's parts aren't redacted by the base, so say it without them
            msg = str(e)
            for v in (self.creds["token"], self.creds["user_id"]): msg = msg.replace(v, "***")
            raise RuntimeError(f"{path}: {msg[:150]}") from None
        if r.get("success") is False: raise RuntimeError(f"{path}: {str(r.get('error', 'failed'))[:100]}")
        return r

    def send(self, chat, text, files=()):
        if text: self.call("POST", "/chat.postMessage", body={"roomId": chat, "text": text})

    def poll_room(self, room, inbound, first):
        rid = room["_id"]
        if first and rid not in self.cursor: self.cursor[rid] = room.get("lm") or ""  # what was said before we started is not replayed
        params = {"roomId": rid, "count": 50, "sort": json.dumps({"ts": 1})}
        if self.cursor.get(rid): params["oldest"] = self.cursor[rid]
        # more than two names is a group conversation, not a private chat with one person
        dm = len(room.get("usernames") or []) <= 2
        for m in self.call("GET", "/im.messages", params).get("messages") or []:
            if m["ts"] <= self.cursor.get(rid, ""): continue
            self.cursor[rid] = m["ts"]
            uid = (m.get("u") or {}).get("_id")
            if m.get("t") or not uid or uid == self.creds["user_id"]: continue  # system lines and our own
            inbound(C.Msg(chat=rid, sender=str(uid), text=m.get("msg", ""), id=m["_id"], dm=dm, name=(m.get("u") or {}).get("username", "")))

    def poll_once(self, inbound, first=False):
        for room in self.call("GET", "/im.list", {"count": 100}).get("ims") or []:
            self.poll_room(room, inbound, first)

    def listen(self, inbound):
        first = True
        while True:
            self.poll_once(inbound, first); first = False
            time.sleep(float(self.cfg.get("poll", 3)))


CONNECTOR = RocketChat
