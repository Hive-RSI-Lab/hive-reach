"""Matrix. Long poll on /sync, so no port. Identity is the sender's MXID; only a room with exactly two joined members counts as private.
No encryption support: an encrypted event is answered once per room with a line saying so. Connects to a server that already exists."""
import json, mimetypes, sys, urllib.parse, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

FILE_TYPES = ("m.file", "m.image", "m.audio", "m.video")
MAX_DOWNLOAD = 25 * 2**20
FILTER = {"presence": {"types": []}, "account_data": {"types": []}, "room": {"ephemeral": {"types": []}, "timeline": {"limit": 50}}}
ENCRYPTED_NOTE = "This room is encrypted and I can't read encrypted messages. Please start a new chat with encryption turned off."


def q(s): return urllib.parse.quote(s, safe="")


class Matrix(C.Connector):
    name = "matrix"; label = "Matrix"; size = 16000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.server = self.cfg.get("server", "").rstrip("/")
        self.me = self.cfg.get("user") or ""

    def ready(self):
        return "no homeserver: set \"server\" in ~/.config/h2/conn/matrix.json" if not self.server else super().ready()

    def state_file(self, n): return C.DATA / self.name / n

    def call(self, method, path, body=None, timeout=60, headers=None, raw=False):
        h = {"Authorization": f"Bearer {self.secret}"} | (headers or {})
        return C.http(method, f"{self.server}{path}", body=body, headers=h, timeout=timeout, raw=raw)

    # sending

    def event(self, room, content):
        self.call("PUT", f"/_matrix/client/v3/rooms/{q(room)}/send/m.room.message/{uuid.uuid4().hex}", content)

    def upload(self, f):
        f = Path(f); kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        r = self.call("POST", f"/_matrix/media/v3/upload?filename={q(f.name)}", f.read_bytes(), timeout=300, headers={"Content-Type": kind})
        return r["content_uri"], kind, f.stat().st_size

    def send(self, chat, text, files=()):
        if text: self.event(chat, {"msgtype": "m.text", "body": text})
        for f in files:
            uri, kind, size = self.upload(f)
            self.event(chat, {"msgtype": "m.file", "body": Path(f).name, "url": uri, "info": {"mimetype": kind, "size": size}})

    # receiving

    def joined(self, room):
        return set(self.call("GET", f"/_matrix/client/v3/rooms/{q(room)}/joined_members").get("joined") or {})

    def fetch(self, content):
        """The attachment of a file event, in a temp folder. One that can't be fetched is named in the text rather than lost silently."""
        name = content.get("body") or "file"
        try:
            if (content.get("info") or {}).get("size", 0) > MAX_DOWNLOAD: raise RuntimeError("too big")
            host, _, media = content["url"].removeprefix("mxc://").partition("/")
            for base in ("/_matrix/client/v1/media/download", "/_matrix/media/v3/download"):  # newer servers want the first, older only have the second
                try:
                    url = f"{self.server}{base}/{q(host)}/{q(media)}"
                    return C.download(url, C.inbox_dir(self.name), name, headers={"Authorization": f"Bearer {self.secret}"}), ""
                except RuntimeError as e:
                    if "HTTP 404" not in str(e) and "HTTP 400" not in str(e): raise
            raise RuntimeError("not found")
        except Exception:
            return None, name

    def handle(self, room, ev, inbound):
        who = ev.get("sender") or ""
        if not who or who == self.me: return
        content, kind = ev.get("content") or {}, ev.get("type")
        if (content.get("m.relates_to") or {}).get("rel_type") == "m.replace": return  # an edit, not a new message
        if kind == "m.room.encrypted": return self.say_encrypted(room, who) if self.trusted(who) else None  # a stranger gets a pairing code at most
        if kind != "m.room.message": return
        mt = content.get("msgtype")
        if mt != "m.text" and mt not in FILE_TYPES: return  # notices are other bots; emotes and the rest aren't requests
        members = self.joined(room)
        dm = len(members) == 2 and who in members
        text, files = content.get("body") or "", []
        if mt in FILE_TYPES:
            text = ""
            if dm and self.trusted(who):  # a stranger's files never reach the disk
                path, failed = self.fetch(content)
                if path: files.append(path)
                else: text = f"(attached a file that couldn't be fetched: {failed})"
        inbound(C.Msg(chat=room, sender=who, text=text, id=ev.get("event_id") or "", dm=dm, name=who, files=files))

    def say_encrypted(self, room, who):
        """Once per private room, then never again, so a chatty person isn't answered every time."""
        p = self.state_file("told_encrypted.json")
        told = set(json.loads(p.read_text())) if p.exists() else set()
        if room in told or len(self.joined(room)) != 2: return  # not a private room: say nothing
        self.event(room, {"msgtype": "m.notice", "body": ENCRYPTED_NOTE})
        told.add(room); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(sorted(told)))

    def invites(self, rooms):
        """Join a room only if the inviter flagged it as a direct chat. A stranger who gets in still only gets a pairing code from the bridge."""
        for room, inv in rooms.items():
            for ev in (inv.get("invite_state") or {}).get("events") or []:
                if ev.get("type") == "m.room.member" and ev.get("state_key") == self.me and (ev.get("content") or {}).get("is_direct") is True:
                    self.call("POST", f"/_matrix/client/v3/join/{q(room)}", {})
                    break

    def sync_once(self, since, inbound):
        """One /sync. The first one (no since token yet) only looks at invites: old history is not replayed."""
        args = {"timeout": 30000 if since else 0, "filter": json.dumps(FILTER)}
        if since: args["since"] = since
        data = self.call("GET", "/_matrix/client/v3/sync?" + urllib.parse.urlencode(args), timeout=60)
        rooms = data.get("rooms") or {}
        self.invites(rooms.get("invite") or {})
        if since:
            for room, r in (rooms.get("join") or {}).items():
                for ev in (r.get("timeline") or {}).get("events") or []: self.handle(room, ev, inbound)
        return data["next_batch"]

    def listen(self, inbound):
        if not self.me: self.me = self.call("GET", "/_matrix/client/v3/account/whoami")["user_id"]
        f = self.state_file("since")
        since = f.read_text().strip() if f.exists() else ""
        while True:
            since = self.sync_once(since, inbound)
            f.parent.mkdir(parents=True, exist_ok=True); f.write_text(since)  # saved after handling: a crash replays, and the bridge drops repeats


CONNECTOR = Matrix
