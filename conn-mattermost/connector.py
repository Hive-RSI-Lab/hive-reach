"""Mattermost: a websocket out for events, REST for replies. Direct messages only (channel_type D); the sender is the user id.
The server is one that already exists; this never hosts anything. Warden's ruling: 1105012730b5."""
import base64, json, os, socket, ssl, struct, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C


class WS:
    """A small websocket client for JSON text frames: handshake, masked sends, ping/pong, close. No extensions, no fragments over 16 MB."""
    def __init__(self, url, timeout=90):
        u = urllib.parse.urlsplit(url); tls = u.scheme in ("wss", "https")
        self.sock = socket.create_connection((u.hostname, u.port or (443 if tls else 80)), timeout=30)
        if tls: self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=u.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        host = u.netloc
        self.sock.sendall((f"GET {u.path or '/'}{'?' + u.query if u.query else ''} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            d = self.sock.recv(1); head += d
            if not d or len(head) > 8192: raise RuntimeError("websocket handshake failed")
        if b" 101 " not in head.split(b"\r\n")[0]: raise RuntimeError("the server refused the websocket")
        self.sock.settimeout(timeout)

    def exact(self, n):
        buf = b""
        while len(buf) < n:
            d = self.sock.recv(n - len(buf))
            if not d: raise RuntimeError("websocket closed")
            buf += d
        return buf

    def frame(self, op, data=b""):
        n, mask = len(data), os.urandom(4)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else b"\xfe" + struct.pack(">H", n) if n < 65536 else b"\xff" + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send_json(self, obj): self.frame(1, json.dumps(obj).encode())

    def recv_json(self):
        """The next JSON message; answers pings itself. Raises when the socket closes or goes quiet."""
        text = b""
        while True:
            b1, b2 = self.exact(2); op, n = b1 & 15, b2 & 127
            if n == 126: n = struct.unpack(">H", self.exact(2))[0]
            elif n == 127: n = struct.unpack(">Q", self.exact(8))[0]
            if n > 16 * 2**20: raise RuntimeError("websocket frame too big")
            data = self.exact(n)  # the server never masks
            if op == 8: raise RuntimeError("websocket closed")
            if op == 9: self.frame(10, data); continue
            if op in (0, 1): text += data
            if b1 & 0x80 and op in (0, 1):
                try: return json.loads(text)
                except ValueError: text = b""

    def close(self):
        try: self.sock.close()
        except OSError: pass


class Mattermost(C.Connector):
    name = "mattermost"; label = "Mattermost"; size = 4000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.base = self.cfg.get("server", "").rstrip("/"); self.me = None

    def ready(self):
        if not self.base: return "no server: `conn set mattermost server https://chat.example.com`"
        return C.plain_refused(self.base, self.cfg) or super().ready()

    def call(self, method, path, body=None):
        return C.http(method, f"{self.base}/api/v4{path}", body=body, headers={"Authorization": "Bearer " + self.secret}, timeout=30)

    def send(self, chat, text, files=()):
        if text: self.call("POST", "/posts", {"channel_id": chat, "message": text})

    def handle(self, ev, inbound):
        if ev.get("event") != "posted": return
        d = ev.get("data") or {}
        try: post = json.loads(d.get("post") or "{}")
        except ValueError: return
        uid = post.get("user_id")
        if not uid or uid == self.me or post.get("type"): return  # our own, or a system line (joins, header changes)
        inbound(C.Msg(chat=post.get("channel_id", ""), sender=str(uid), text=post.get("message", ""), id=post.get("id", ""),
                      dm=d.get("channel_type") == "D", name=d.get("sender_name", "").lstrip("@")))

    def listen(self, inbound):
        self.me = self.call("GET", "/users/me")["id"]
        ws = WS(self.base.replace("http", "ws", 1) + "/api/v4/websocket", timeout=float(self.cfg.get("idle", 90)))
        try:
            ws.send_json({"seq": 1, "action": "authentication_challenge", "data": {"token": self.secret}})
            while True: self.handle(ws.recv_json(), inbound)
        finally: ws.close()


CONNECTOR = Mattermost
