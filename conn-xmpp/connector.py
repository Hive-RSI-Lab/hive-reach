"""XMPP: chat-type messages only, sender is the bare JID (the server vouches for `from` on a client connection). groupchat is dm=False.
We never join a room. slixmpp is imported inside functions so the pure parts run and test without it. Warden's ruling: 1105012730b5."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


def bare(jid):
    """user@host/resource -> user@host, lower case (the domain and node are case-insensitive)."""
    return str(jid).split("/", 1)[0].lower()


def to_msg(mtype, frm, body, mid=""):
    """A stanza's parts -> Msg, or None when it isn't a message with words. Only type=chat is a private chat."""
    if not body or not frm or mtype not in ("chat", "groupchat"): return None
    who = bare(frm)
    return C.Msg(chat=who, sender=who, text=body, id=f"{who}:{mid}" if mid else "", dm=(mtype == "chat"))


class Xmpp(C.Connector):
    name = "xmpp"; label = "XMPP"; size = 4000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.loop, self.client = None, None

    def ready(self):
        if not self.cfg.get("jid"): return "no account: `conn set xmpp jid bot@example.org`"
        return "" if self.secret else "no password: save it as conn-xmpp with the dashboard's lock"

    def on_message(self, st, inbound):
        """st is a slixmpp Message (anything indexable like one works)."""
        m = to_msg(st["type"], st["from"].full if hasattr(st["from"], "full") else st["from"], st["body"], st["id"])
        if m and m.sender != bare(self.cfg["jid"]): inbound(m)

    def send(self, chat, text, files=()):
        if not (self.client and self.loop): raise RuntimeError("not connected")
        fut = asyncio.run_coroutine_threadsafe(self.say(chat, text), self.loop)
        fut.result(30)

    async def say(self, chat, text):
        self.client.send_message(mto=chat, mbody=text, mtype="chat")

    async def main(self, inbound):
        import slixmpp  # the package is named in module.json; uv fetches it when the service starts
        x = slixmpp.ClientXMPP(self.cfg["jid"], self.secret)
        x.enable_plaintext = False; x.enable_direct_tls = bool(self.cfg.get("direct_tls", False))
        x["feature_mechanisms"].unencrypted_plain = False  # the password never crosses an unencrypted link
        gone = asyncio.get_running_loop().create_future()
        x.add_event_handler("message", lambda st: self.on_message(st, inbound))
        x.add_event_handler("session_start", lambda e: x.send_presence())
        x.add_event_handler("disconnected", lambda e: gone.done() or gone.set_result(None))
        x.add_event_handler("failed_auth", lambda e: gone.done() or gone.set_exception(RuntimeError("the server refused the login")))
        self.client, self.loop = x, asyncio.get_running_loop()
        try:
            if self.cfg.get("host"): x.connect(self.cfg["host"], int(self.cfg.get("port", 5223 if self.cfg.get("direct_tls") else 5222)))
            else: x.connect()  # finds the server from the account's domain
            await gone
        finally:
            self.client = self.loop = None

    def listen(self, inbound):
        asyncio.run(self.main(inbound))
        raise RuntimeError("disconnected")


CONNECTOR = Xmpp
