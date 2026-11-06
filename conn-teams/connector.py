"""Microsoft Teams, outgoing only, through a Workflows webhook ("Post to a channel when a webhook request is received"). The secret is the
webhook URL itself, so it is never logged or put in config. Workflows expects an Adaptive Card inside a "message" envelope; the old
{"text": ...} form of the retired Office 365 connectors is not accepted. Warden's ruling: 1105012730b5."""
import sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


def url_problem(url):
    u = urllib.parse.urlsplit(url or "")
    if u.scheme == "https" and u.hostname: return ""
    if u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"): return ""
    return "the webhook URL must start with https://"


def card(text):
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
        "body": [{"type": "TextBlock", "text": text, "wrap": True}]}}]}


class Teams(C.Connector):
    name = "teams"; label = "Microsoft Teams"; size = 4000; can_receive = False

    def ready(self):
        if not self.secret: return "no webhook: save the channel's Workflows webhook URL as conn-teams with the dashboard's lock"
        return url_problem(self.secret)

    def setup(self):
        return {} if self.cfg.get("home") else {"pings": "short", "home": "channel"}

    def send(self, chat, text, files=()):
        if text: C.http("POST", self.secret, body=card(text), timeout=30)


CONNECTOR = Teams
