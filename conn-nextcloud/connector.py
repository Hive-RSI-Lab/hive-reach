"""Nextcloud Talk: poll over OCS. One-to-one rooms only (type 1); the sender is the actorId of an actorType "users" message (guests and
bots have no fixed user id, so they're ignored). The server already exists; this never hosts one. Warden's ruling: 1105012730b5."""
import base64, sys, time, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

ONE_TO_ONE = 1


class Nextcloud(C.Connector):
    name = "nextcloud"; label = "Nextcloud Talk"; size = 4000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.base = self.cfg.get("server", "").rstrip("/")
        self.cursor = {}  # room token -> newest message id seen

    def ready(self):
        if not self.base or not self.cfg.get("user"): return "no server or user: `conn set nextcloud server https://cloud.example.com` and `conn set nextcloud user botname`"
        if why := C.plain_refused(self.base, self.cfg): return why
        return "" if self.secret else "no app password: save it as conn-nextcloud with the dashboard's lock"

    def call(self, method, path, params=None, body=None):
        auth = base64.b64encode(f"{self.cfg['user']}:{self.secret}".encode()).decode()
        h = {"Authorization": "Basic " + auth, "OCS-APIRequest": "true", "Accept": "application/json"}
        url = f"{self.base}/ocs/v2.php/apps/spreed/api/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
        try: r = C.http(method, url, body=body, headers=h, timeout=30)
        except RuntimeError as e:
            if str(e).startswith("HTTP 304"): return []  # nothing new
            raise
        return (r.get("ocs") or {}).get("data", [])

    def send(self, chat, text, files=()):
        if text: self.call("POST", f"v1/chat/{urllib.parse.quote(chat, safe='')}", body={"message": text})

    def accept(self, msg):
        return (msg.get("actorType") == "users" and msg.get("actorId") and msg["actorId"] != self.cfg["user"]
                and not msg.get("systemMessage") and msg.get("messageType", "comment") == "comment")

    def poll_room(self, room, inbound, first):
        tok = room["token"]
        if tok not in self.cursor:  # a room that was already there at the start is not replayed; one made later is read from the top
            self.cursor[tok] = (room.get("lastMessage") or {}).get("id", 0) if first else 0
        msgs = self.call("GET", f"v1/chat/{urllib.parse.quote(tok, safe='')}",
                         {"lookIntoFuture": 1, "timeout": 0, "limit": 100, "lastKnownMessageId": self.cursor[tok], "setReadMarker": 0})
        for m in sorted(msgs or [], key=lambda x: x["id"]):
            self.cursor[tok] = max(self.cursor[tok], m["id"])
            if self.accept(m):
                inbound(C.Msg(chat=tok, sender=str(m["actorId"]), text=m.get("message", ""), id=f"{tok}:{m['id']}", name=m.get("actorDisplayName", "")))

    def poll_once(self, inbound, first=False):
        for room in self.call("GET", "v4/room") or []:
            if room.get("type") == ONE_TO_ONE: self.poll_room(room, inbound, first)  # groups, public rooms, changelogs: not read at all

    def listen(self, inbound):
        first = True
        while True:
            self.poll_once(inbound, first); first = False
            time.sleep(float(self.cfg.get("poll", 3)))


CONNECTOR = Nextcloud
