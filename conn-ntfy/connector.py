"""ntfy push. Anyone who knows a topic on the public server can read and publish, so there it's contentless and one way (warden, 1105012730b5).
No account. The topic is a long random name, made by `conn on ntfy`."""
import secrets, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

LINE = "H2 has a message for you."
CLICK = "https://hive.example.org"


class Ntfy(C.Connector):
    name = "ntfy"; label = "ntfy"; can_receive = False

    def ready(self):
        if not self.cfg.get("topic"): return "no topic yet: `conn on ntfy` makes one"
        server = self.cfg.get("server", C_SERVER)
        return C.plain_refused(server, self.cfg) if self.secret and own(server) else ""

    def setup(self):
        changes = {}
        if not self.cfg.get("topic"):
            changes = {"topic": "h2-" + secrets.token_urlsafe(18), "pings": "short", "home": "phone"}
            print(f"Subscribe to this in the ntfy app: {self.cfg.get('server', C_SERVER)}/{changes['topic']}")
        return changes

    def send(self, chat, text, files=()):
        """The words are dropped here on purpose, not by policy above: nothing an agent writes reaches a public server."""
        server = self.cfg.get("server", C_SERVER).rstrip("/")
        h = {"Title": "H2", "Click": self.cfg.get("click", CLICK), "Priority": str(self.cfg.get("priority", 3))}
        # A server of the person's own, with a token, may carry the words; a token never goes in the clear
        mine = bool(self.secret) and own(server) and not C.plain_refused(server, self.cfg)
        if mine: h["Authorization"] = "Bearer " + self.secret
        body = text if mine else LINE
        C.http("POST", f"{server}/{self.cfg['topic']}", body=body.encode(), headers=h, timeout=30)


C_SERVER = "https://ntfy.sh"


def own(server):
    """Not the public server, however it's written: https://NTFY.sh/, https://ntfy.sh:443 and http://ntfy.sh are all ntfy.sh."""
    host = C.origin(server)[1].rstrip(".")
    return C.origin(server)[1:] != C.origin(C_SERVER)[1:] and host != "ntfy.sh" and not host.endswith(".ntfy.sh")
CONNECTOR = Ntfy
