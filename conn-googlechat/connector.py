"""Google Chat, outgoing only, through an incoming webhook for one space. The secret is the webhook URL itself (it carries its own key and
token), so it is never logged or put in config. Warden's ruling: 1105012730b5."""
import sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


def url_problem(url):
    """'' when the URL is fit to post to: https, or loopback for a fake. A webhook URL is a credential, so nothing in the clear."""
    u = urllib.parse.urlsplit(url or "")
    if u.scheme == "https" and u.hostname: return ""
    if u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"): return ""
    return "the webhook URL must start with https://"


class GoogleChat(C.Connector):
    name = "googlechat"; label = "Google Chat"; size = 4000; can_receive = False

    def ready(self):
        if not self.secret: return "no webhook: save the space's webhook URL as conn-googlechat with the dashboard's lock"
        return url_problem(self.secret)

    def setup(self):
        return {} if self.cfg.get("home") else {"pings": "short", "home": "space"}

    def send(self, chat, text, files=()):
        if text: C.http("POST", self.secret, body={"text": text}, timeout=30)


CONNECTOR = GoogleChat
