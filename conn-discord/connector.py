"""Discord. The gateway websocket goes out, so no port. Identity is the author's snowflake id; only direct messages count.
Replies go by REST. The websocket client is a small stdlib one, enough for the gateway, so no package is needed."""
import base64, hashlib, json, os, socket, ssl, struct, sys, time, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
API = "https://discord.com/api/v10"
DM_INTENT = 1 << 12  # DIRECT_MESSAGES only: server messages are never even sent to us. DMs don't need the message content intent.
MAX_DOWNLOAD = 25 * 2**20
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Closed(ConnectionError):
    def __init__(self, code): super().__init__(f"gateway closed ({code})"); self.code = code


class WS:
    """Client side of RFC 6455: text frames, ping/pong, close. recv() gives None on a timeout and keeps any partial frame."""

    def __init__(self, url, timeout=10):
        u = urllib.parse.urlparse(url)
        tls = u.scheme == "wss"
        s = socket.create_connection((u.hostname, u.port or (443 if tls else 80)), timeout=timeout)
        if tls: s = ssl.create_default_context().wrap_socket(s, server_hostname=u.hostname)
        self.sock, self.buf, self.parts = s, b"", b""
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        s.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = s.recv(4096)
            if not chunk: raise ConnectionError("gateway closed during handshake")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if " 101" not in lines[0] or want not in head.decode("latin-1"): raise ConnectionError("gateway refused the upgrade")

    def _frame(self, data):
        """Pull one whole frame off the front of data: (fin, opcode, payload, rest), or None if it isn't all here yet."""
        if len(data) < 2: return None
        fin, op, n, i = data[0] & 0x80, data[0] & 15, data[1] & 0x7F, 2
        if n == 126:
            if len(data) < 4: return None
            n, i = struct.unpack(">H", data[2:4])[0], 4
        elif n == 127:
            if len(data) < 10: return None
            n, i = struct.unpack(">Q", data[2:10])[0], 10
        if len(data) < i + n: return None
        return fin, op, data[i:i + n], data[i + n:]

    def send(self, op, payload=b""):
        mask = os.urandom(4); n = len(payload)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                      else bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[k % 4] for k, b in enumerate(payload)))

    def send_text(self, text): self.send(1, text.encode())

    def recv(self, timeout):
        """The next text message, or None if nothing whole arrived within timeout seconds."""
        end = time.time() + timeout
        while True:
            f = self._frame(self.buf)
            if f:
                fin, op, payload, self.buf = f
                if op == 9: self.send(10, payload); continue  # ping
                if op == 10: continue
                if op == 8: raise Closed(struct.unpack(">H", payload[:2])[0] if len(payload) > 1 else 0)
                self.parts += payload
                if fin:
                    out, self.parts = self.parts, b""
                    return out.decode("utf-8", "replace")
                continue
            left = end - time.time()
            if left <= 0: return None
            self.sock.settimeout(left)
            try: chunk = self.sock.recv(65536)
            except (socket.timeout, TimeoutError): return None
            if not chunk: raise ConnectionError("gateway closed")
            self.buf += chunk

    def close(self):
        try: self.send(8, struct.pack(">H", 1000))
        except OSError: pass
        try: self.sock.close()
        except OSError: pass


class Discord(C.Connector):
    name = "discord"; label = "Discord"; size = 1900  # the real limit is 2000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.api = self.cfg.get("api", API).rstrip("/")
        self.session = self.resume_url = None
        self.seq = None

    def call(self, method, path, body=None, timeout=60, headers=None):
        h = {"Authorization": f"Bot {self.secret}", "User-Agent": "DiscordBot (https://h2, 1)"} | (headers or {})
        return C.http(method, f"{self.api}{path}", body=body, headers=h, timeout=timeout)

    def send(self, chat, text, files=()):
        path = f"/channels/{chat}/messages"
        if text: self.call("POST", path, {"content": text, "allowed_mentions": {"parse": []}})
        for f in files:
            body, ctype = C.multipart({"payload_json": json.dumps({"allowed_mentions": {"parse": []}})}, [("files[0]", f)])
            self.call("POST", path, body, timeout=300, headers={"Content-Type": ctype})

    def fetch(self, msg):
        """Attachments, in a temp folder. One that can't be fetched is named in the text rather than lost silently."""
        paths, failed, dest = [], [], None
        for a in msg.get("attachments") or []:
            name = a.get("filename") or "file"
            try:
                if (a.get("size") or 0) > MAX_DOWNLOAD: raise RuntimeError("too big")
                dest = dest or C.inbox_dir(self.name)
                paths.append(C.download(a["url"], dest, name))  # CDN links are signed: no token sent there
            except Exception:
                failed.append(name)
        return paths, failed

    def handle(self, msg, inbound):
        """A MESSAGE_CREATE. No guild_id means a DM; anything else is marked so the bridge drops it, and nothing is fetched."""
        who = msg.get("author") or {}
        if not who.get("id") or who.get("bot") or msg.get("webhook_id"): return
        if msg.get("type", 0) not in (0, 19): return  # joins, pins and so on aren't messages to us
        dm = not msg.get("guild_id")
        text = msg.get("content") or ""
        files, failed = self.fetch(msg) if dm and self.trusted(who["id"]) else ([], [])  # a stranger's files never reach the disk
        if failed: text += "\n(attached files that couldn't be fetched: " + ", ".join(failed) + ")"
        inbound(C.Msg(chat=str(msg.get("channel_id")), sender=str(who["id"]), text=text, id=str(msg.get("id")), dm=dm,
                      name=who.get("username") or "", files=files))

    def identify(self):
        return {"op": 2, "d": {"token": self.secret, "intents": DM_INTENT,
                               "properties": {"os": "linux", "browser": "h2-conn", "device": "h2-conn"}}}

    def start(self, ws):
        """Resume the old session if we have one, else start a new one."""
        if self.session and self.seq is not None:
            ws.send_text(json.dumps({"op": 6, "d": {"token": self.secret, "session_id": self.session, "seq": self.seq}}))
        else: ws.send_text(json.dumps(self.identify()))

    def dispatch(self, ev, inbound):
        """One gateway message. Returns False when the connection should be dropped and made again."""
        op = ev.get("op")
        if ev.get("s") is not None: self.seq = ev["s"]
        if op == 0:
            if ev.get("t") == "READY":
                d = ev.get("d") or {}
                self.session, self.resume_url = d.get("session_id"), d.get("resume_gateway_url")
            elif ev.get("t") == "MESSAGE_CREATE": self.handle(ev.get("d") or {}, inbound)
        elif op == 7: return False                       # asked to reconnect
        elif op == 9:                                    # session no longer valid
            if not ev.get("d"): self.session, self.seq = None, None
            time.sleep(self.cfg.get("invalid_wait", 3))  # Discord asks for a short pause before trying again
            return False
        return True

    def session_loop(self, ws, inbound):
        """Heartbeat on schedule; if the last one was never acknowledged the link is dead, so leave and reconnect."""
        hello = json.loads(ws.recv(30) or "{}")
        if hello.get("op") != 10: raise ConnectionError("no hello from the gateway")
        every = hello["d"]["heartbeat_interval"] / 1000
        self.start(ws)
        next_beat, acked = time.time() + every * 0.5, True  # first beat is jittered, as documented
        while True:
            now = time.time()
            if now >= next_beat:
                if not acked: raise ConnectionError("heartbeat not acknowledged")
                ws.send_text(json.dumps({"op": 1, "d": self.seq})); acked, next_beat = False, now + every
            raw = ws.recv(max(0.05, min(next_beat - now, 1)))
            if raw is None: continue
            ev = json.loads(raw)
            if ev.get("op") == 11: acked = True
            elif ev.get("op") == 1: next_beat = 0     # asked for a beat right now
            elif not self.dispatch(ev, inbound): return

    def listen(self, inbound):
        while True:
            url = self.cfg.get("gateway", GATEWAY)
            if self.session and self.resume_url and not self.cfg.get("gateway"):  # Discord names a better address for resuming
                url = self.resume_url.rstrip("/") + "/?v=10&encoding=json"
            ws = WS(url)
            try: self.session_loop(ws, inbound)
            except Closed as e:
                if e.code in (4004, 4010, 4011, 4012, 4013, 4014):
                    raise RuntimeError(f"Discord refused the bot (close code {e.code}): check the token and intents") from None
                if e.code in (4007, 4009): self.session = self.seq = None  # the session is over: start fresh
                raise
            finally: ws.close()


CONNECTOR = Discord
