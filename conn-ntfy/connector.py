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
        return "" if self.cfg.get("topic") else "no topic yet: `conn on ntfy` makes one"

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
        # A server of the person's own, with a token, may carry the words
        if self.secret and server != C_SERVER: h["Authorization"] = "Bearer " + self.secret
        body = text if self.secret and server != C_SERVER else LINE
        C.http("POST", f"{server}/{self.cfg['topic']}", body=body.encode(), headers=h, timeout=30)


C_SERVER = "https://ntfy.sh"
CONNECTOR = Ntfy
