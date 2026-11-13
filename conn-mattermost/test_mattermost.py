"""Against a fake Mattermost (REST + websocket on loopback): python3 -I test_mattermost.py"""
import base64, hashlib, http.server, json, os, struct, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as M

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def post(uid, text, ctype="D", **kw):
    p = {"id": kw.get("id", "p" + text), "user_id": uid, "channel_id": "chan" + uid, "message": text, "type": kw.get("type", "")}
    return {"event": "posted", "data": {"channel_type": ctype, "sender_name": "@" + uid, "post": json.dumps(p)}}


class Fake(http.server.BaseHTTPRequestHandler):
    events, posts, auths, seen_auth = [], [], [], []
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def json(self, obj):
        out = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        if self.path == "/api/v4/users/me":
            Fake.seen_auth.append(self.headers.get("Authorization")); return self.json({"id": "botid"})
        if self.path == "/api/v4/websocket": return self.ws()
        self.send_error(404)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.posts.append(body); self.json({"id": "x"})
    def ws(self):
        acc = base64.b64encode(hashlib.sha1(self.headers["Sec-WebSocket-Key"].encode() + GUID).digest()).decode()
        self.wfile.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
        self.wfile.flush()
        b1, b2 = self.rfile.read(2); n = b2 & 127
        if n == 126: n = struct.unpack(">H", self.rfile.read(2))[0]
        mask = self.rfile.read(4); data = bytes(c ^ mask[i % 4] for i, c in enumerate(self.rfile.read(n)))
        Fake.auths.append(json.loads(data))
        self.wfile.write(b"\x89\x02hi"); self.wfile.flush()  # a ping first
        for ev in Fake.events:
            d = json.dumps(ev).encode()
            head = b"\x81" + (bytes([len(d)]) if len(d) < 126 else b"\x7e" + struct.pack(">H", len(d)))
            self.wfile.write(head + d)
        self.wfile.write(b"\x88\x00"); self.wfile.flush()
        self.close_connection = True


class T(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.events, Fake.posts, Fake.auths, Fake.seen_auth = [], [], [], []
        self.c = M.Mattermost({"server": f"http://127.0.0.1:{self.srv.server_port}"}, "TOK")
    def tearDown(self): self.srv.shutdown()

    def run_listen(self):
        got = []
        with self.assertRaises(RuntimeError): self.c.listen(got.append)
        return got

    def test_dm_uses_user_id_and_others_are_not_dm(self):
        Fake.events = [post("u1", "hi"), post("u2", "in a channel", "O"), post("u3", "private channel", "P"), post("botid", "mine"),
                       post("u1", "joined", type="system_join_channel"), {"event": "typing", "data": {}}, post("u1", "x" * 300, id="long")]
        got = self.run_listen()
        self.assertEqual([(m.sender, m.dm, m.text[:5]) for m in got], [("u1", True, "hi"), ("u2", False, "in a "), ("u3", False, "priva"), ("u1", True, "xxxxx")])
        self.assertEqual(got[0].chat, "chanu1")
        self.assertEqual(Fake.auths[0]["data"]["token"], "TOK"); self.assertEqual(Fake.seen_auth, ["Bearer TOK"])

    def test_send_posts_to_the_channel(self):
        self.c.send("chan1", "hello"); self.assertEqual(Fake.posts, [{"channel_id": "chan1", "message": "hello"}])

    def test_ready(self):
        self.assertIn("server", M.Mattermost({}, "t").ready()); self.assertIn("token", M.Mattermost({"server": "https://x"}, "").ready()); self.assertIn("https", M.Mattermost({"server": "http://chat.lan"}, "t").ready())
        self.assertEqual(self.c.ready(), "")


if __name__ == "__main__": unittest.main()
