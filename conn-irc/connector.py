"""IRC, private messages only, over TLS. A nick isn't fixed on a public network, so the sender is the services account the server vouches
for in the message's `account` tag (IRCv3 account-tag), never the nick. No account: no identity, and the message is dropped with no reply.
We never join a channel. Warden's ruling: 1105012730b5."""
import base64, socket, ssl, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

WANT = ("sasl", "account-tag", "account-notify")
NEED = ("sasl", "account-tag")  # without these there is no identity at all
LINE = 400                      # bytes of text per line: the wire limit is 512 with the prefix and tags


def parse(line):
    """':nick!u@h CMD a b :trailing' with optional '@tags ' in front -> (tags, nick, cmd, params)."""
    tags, nick = {}, ""
    if line.startswith("@"):
        raw, _, line = line.partition(" ")
        for kv in raw[1:].split(";"):
            k, _, v = kv.partition("="); tags[k] = v
    if line.startswith(":"):
        src, _, line = line[1:].partition(" "); nick = src.split("!")[0]
    head, sep, trail = line.partition(" :")
    params = head.split()
    cmd = params.pop(0).upper() if params else ""
    return tags, nick, cmd, params + ([trail] if sep else [])


def clean(s):
    return s.replace("\r", "").replace("\0", "")


def fit(text, size=LINE):
    """Lines of at most `size` bytes, cut on character boundaries."""
    out = []
    for raw in clean(text).split("\n"):
        while len(raw.encode()) > size:
            n = size
            while len(raw[:n].encode()) > size: n -= 1
            out.append(raw[:n]); raw = raw[n:]
        if raw.strip(): out.append(raw)
    return out


def account_of(tags):
    a = tags.get("account", "")
    return "" if a in ("", "*", "0") else a


class Irc(C.Connector):
    name = "irc"; label = "IRC"; size = 400

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.sock, self.wlock, self.nick = None, threading.Lock(), self.cfg.get("nick", "")
        self.nicks = {}  # account -> the nick that last wrote to us, which is where a reply goes

    def ready(self):
        if not self.cfg.get("server") or not self.cfg.get("nick"): return "no server or nick: `conn set irc server irc.example.net` and `conn set irc nick mybot`"
        if self.cfg.get("tls") is False: return "TLS is required; this connector won't talk in the clear"
        return "" if self.secret else "no SASL password: save it as conn-irc with the dashboard's lock"

    # wire
    def write(self, line):
        with self.wlock:
            if not self.sock: raise RuntimeError("not connected")
            self.sock.sendall(clean(line).replace("\n", " ").encode()[:510] + b"\r\n")

    def connect(self):
        ctx = ssl.create_default_context(cafile=self.cfg.get("cafile"))  # cafile: a private CA of the person's own server
        raw = socket.create_connection((self.cfg["server"], int(self.cfg.get("port", 6697))), timeout=30)
        host = self.cfg["server"]
        return ctx.wrap_socket(raw, server_hostname=host)

    def send(self, chat, text, files=()):
        nick = self.nicks.get(str(chat))
        if not nick: raise RuntimeError("no one to reply to yet: they have to write first since the bot started")
        for line in fit(text): self.write(f"PRIVMSG {nick} :{line}")

    # state machine for one line from the server; returns False to stop
    def on_line(self, line, inbound, st):
        tags, nick, cmd, p = parse(line)
        if cmd == "PING": self.write("PONG :" + (p[-1] if p else ""))
        elif cmd == "CAP" and len(p) > 1: self.on_cap(p, st)
        elif cmd == "AUTHENTICATE" and p == ["+"]: self.auth()
        elif cmd == "903": self.write("CAP END")
        elif cmd in ("902", "904", "905", "906", "907"): raise RuntimeError("the server refused the SASL login")
        elif cmd == "001": self.nick = p[0]; st["up"] = True
        elif cmd in ("433", "432", "436"): self.nick += "_"; self.write("NICK " + self.nick)
        elif cmd == "PONG": st["ping"] = False
        elif cmd in ("NICK", "QUIT"):  # that nick may not be them any more; a reply waits until they write again
            for acct in [a for a, n in self.nicks.items() if n.lower() == (nick or "").lower()]: del self.nicks[acct]
        elif cmd == "PRIVMSG" and len(p) >= 2: self.on_msg(tags, nick, p[0], p[1], inbound)
        elif cmd == "ERROR": raise RuntimeError("server closed the connection")

    def on_cap(self, p, st):
        sub = p[1].upper()
        if sub == "LS":
            st["caps"] = st.get("caps", set()) | {c.split("=")[0] for c in p[-1].split()}
            if p[-2] == "*": return  # more of the list is coming
            if any(c not in st["caps"] for c in NEED): raise RuntimeError("the server can't tell us who people are (needs SASL and account-tag)")
            self.write("CAP REQ :" + " ".join(c for c in WANT if c in st["caps"]))
        elif sub == "ACK": self.write("AUTHENTICATE PLAIN")
        elif sub == "NAK": raise RuntimeError("the server refused the capabilities we need")

    def auth(self):
        user = self.cfg.get("sasl_user") or self.cfg["nick"]
        blob = base64.b64encode(f"\0{user}\0{self.secret}".encode()).decode()
        parts = [blob[i:i + 400] for i in range(0, len(blob), 400)] or ["+"]
        if len(blob) % 400 == 0: parts.append("+")
        for part in parts: self.write("AUTHENTICATE " + part)

    def on_msg(self, tags, nick, target, text, inbound):
        if nick.lower() == self.nick.lower(): return
        if target.lower() != self.nick.lower():
            inbound(C.Msg(chat=target, sender="", text="", dm=False)); return  # a channel: said nowhere, kept nowhere
        account = account_of(tags)
        if not account: return  # not logged in: no identity, no reply
        self.nicks[account] = nick
        inbound(C.Msg(chat=account, sender=account, text=text, id=tags.get("msgid", ""), name=nick))

    def listen(self, inbound):
        self.sock = self.connect()
        st = {"ping": False}
        try:
            self.write("CAP LS 302"); self.write("NICK " + self.nick); self.write(f"USER {self.cfg['nick']} 0 * :H2")
            buf = b""; self.sock.settimeout(float(self.cfg.get("idle", 240)))
            while True:
                try: data = self.sock.recv(4096)
                except socket.timeout:
                    if st["ping"]: raise RuntimeError("the server went quiet")
                    st["ping"] = True; self.write("PING :h2"); continue
                if not data: raise RuntimeError("connection closed")
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").rstrip("\r")
                    if line: self.on_line(line, inbound, st)
        finally:
            with self.wlock:
                s, self.sock = self.sock, None
            try: s.close()
            except OSError: pass


CONNECTOR = Irc
