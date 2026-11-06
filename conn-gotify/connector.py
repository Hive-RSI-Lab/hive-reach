"""Gotify push to a server the person already runs. One way. Content-free ("something is waiting") unless the server is https and the
person set carry_words: true, so words never cross a link anyone can read. Warden's ruling: 1105012730b5."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

LINE = "H2 has a message for you."


class Gotify(C.Connector):
    name = "gotify"; label = "Gotify"; size = 3000; can_receive = False

    def ready(self):
        if not self.cfg.get("server"): return "no server: `conn set gotify server https://gotify.example.com`"
        return "" if self.secret else "no app token: save it as conn-gotify with the dashboard's lock"

    def setup(self):
        return {} if self.cfg.get("home") else {"pings": "short", "home": "phone"}

    def carries(self):
        """Words go out only over https, and only when the person said so. Enforced here, not by what the bridge sends."""
        return self.cfg.get("server", "").lower().startswith("https://") and self.cfg.get("carry_words") is True

    def send(self, chat, text, files=()):
        body = text if self.carries() and text else LINE
        # the token goes in a header, not the URL, so it can't turn up in an error or a server log line
        C.http("POST", self.cfg["server"].rstrip("/") + "/message", body={"title": "H2", "message": body, "priority": int(self.cfg.get("priority", 5))},
               headers={"X-Gotify-Key": self.secret}, timeout=30)


CONNECTOR = Gotify
