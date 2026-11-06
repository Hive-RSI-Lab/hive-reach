"""Against a fake gateway and REST API on loopback: python3 -I test_discord.py"""
import base64, hashlib, http.server, json, os, socket, struct, sys, tempfile, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as D


class Rest(http.server.BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Rest.calls.append((self.path, dict(self.headers), body))
        out = b"{}"; self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "7"); self.end_headers(); self.wfile.write(b"PDFDATA")


def frame(op, payload):
    n = len(payload)
    head = bytes([0x80 | op]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n))
    return head + payload


class FakeGateway:
    """Accepts connections one after another; each gets the script: a list of strings to send after reading the client's first message."""
    def __init__(self, scripts):
        self.scripts, self.seen = list(scripts), []
        self.srv = socket.socket(); self.srv.bind(("127.0.0.1", 0)); self.srv.listen(5)
        self.url = f"ws://127.0.0.1:{self.srv.getsockname()[1]}/"
        threading.Thread(target=self.run, daemon=True).start()

    def read_frame(self, c):
        buf = b""
        while len(buf) < 2: buf += c.recv(1)
        n = buf[1] & 0x7F
        if n == 126: n = struct.unpack(">H", c.recv(2))[0]
        mask = c.recv(4); data = b""
        while len(data) < n: data += c.recv(n - len(data))
        return buf[0] & 15, bytes(b ^ mask[i % 4] for i, b in enumerate(data))

    def run(self):
        while self.scripts:
            c, _ = self.srv.accept(); script = self.scripts.pop(0)
            req = b""
            while b"\r\n\r\n" not in req: req += c.recv(1024)
            key = [l.split(": ")[1] for l in req.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
            acc = base64.b64encode(hashlib.sha1((key + D.GUID).encode()).digest()).decode()
            c.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
            try:
                for step in script:
                    if step == "read":
                        op, data = self.read_frame(c)
                        if op == 1: self.seen.append(json.loads(data))  # control frames (pong, close) aren't gateway messages
                    elif step == "ping": c.sendall(frame(9, b"hi"))
                    elif step == "close4007": c.sendall(frame(8, struct.pack(">H", 4007)))
                    elif step == "close4004": c.sendall(frame(8, struct.pack(">H", 4004)))
                    elif step == "drop": break
                    else: c.sendall(frame(1, json.dumps(step).encode()))
            except OSError: pass
            time.sleep(0.2); c.close()


HELLO = {"op": 10, "d": {"heartbeat_interval": 100}}
READY = {"op": 0, "t": "READY", "s": 1, "d": {"session_id": "S1", "resume_gateway_url": "ws://unused"}}
def create(i, text, author="42", guild=None, bot=False, chan="900"):
    d = {"id": str(i), "channel_id": chan, "content": text, "author": {"id": author, "username": "someone", "bot": bot}, "type": 0}
    if guild: d["guild_id"] = guild
    return {"op": 0, "t": "MESSAGE_CREATE", "s": i, "d": d}


class T1(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Rest)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Rest.calls = []
        C.DATA = Path(tempfile.mkdtemp())
        self.c = D.Discord({"api": f"http://127.0.0.1:{self.srv.server_port}", "invalid_wait": 0, "gateway": "ws://127.0.0.1:9/"}, "SEKRET")  # a dead address, so no test can reach the real gateway

    def tearDown(self): self.srv.shutdown()

    def got(self, msg):
        out = []; self.c.handle(msg, out.append); return out

    def test_dm_uses_author_id_not_name(self):
        m = self.got(create(5, "hi")["d"])[0]
        self.assertEqual((m.sender, m.chat, m.dm, m.text, m.id), ("42", "900", True, "hi", "5"))

    def test_guild_message_is_marked_and_fetches_nothing(self):
        d = create(6, "x", guild="g1")["d"]; d["attachments"] = [{"url": f"http://127.0.0.1:{self.srv.server_port}/a", "filename": "a.pdf"}]
        m = self.got(d)[0]
        self.assertFalse(m.dm); self.assertEqual(m.files, [])

    def test_bots_webhooks_and_system_messages_ignored(self):
        self.assertEqual(self.got(create(7, "x", bot=True)["d"]), [])
        d = create(8, "x")["d"]; d["webhook_id"] = "w"; self.assertEqual(self.got(d), [])
        d = create(9, "x")["d"]; d["type"] = 7; self.assertEqual(self.got(d), [])

    def test_a_strangers_file_is_not_fetched(self):
        d = create(12, "")["d"]; d["attachments"] = [{"url": f"http://127.0.0.1:{self.srv.server_port}/a", "filename": "a.pdf"}]
        self.assertEqual(self.got(d)[0].files, []); self.assertEqual(Rest.calls, [])

    def test_attachment_lands_on_disk_under_a_safe_name(self):
        self.c.trusted = lambda s: True
        d = create(10, "")["d"]; d["attachments"] = [{"url": f"http://127.0.0.1:{self.srv.server_port}/a", "filename": "../a.pdf"}]
        m = self.got(d)[0]
        self.assertEqual(m.files[0].read_bytes(), b"PDFDATA"); self.assertNotIn("..", m.files[0].name)

    def test_too_big_is_named_not_lost(self):
        self.c.trusted = lambda s: True
        d = create(11, "see")["d"]; d["attachments"] = [{"url": "http://x/", "filename": "big.bin", "size": 30 * 2**20}]
        m = self.got(d)[0]
        self.assertIn("big.bin", m.text); self.assertEqual(m.files, [])

    def test_send_text_and_file_with_bot_auth_and_no_pings(self):
        f = Path(tempfile.mkdtemp()) / "x.txt"; f.write_text("data")
        self.c.send("900", "hello @everyone", [f])
        self.assertEqual([c[0] for c in Rest.calls], ["/channels/900/messages"] * 2)
        self.assertEqual(Rest.calls[0][1]["Authorization"], "Bot SEKRET")
        self.assertEqual(json.loads(Rest.calls[0][2])["allowed_mentions"], {"parse": []})
        self.assertIn(b"data", Rest.calls[1][2]); self.assertIn(b'name="files[0]"', Rest.calls[1][2])

    def test_size_is_under_the_discord_limit(self): self.assertLessEqual(D.Discord.size, 1900)

    def test_intent_is_direct_messages_only(self):
        self.assertEqual(self.c.identify()["d"]["intents"], 4096)

    def listen(self, scripts, count):
        gw = FakeGateway(scripts); self.c.cfg["gateway"] = gw.url; got = []
        def inbound(m):
            got.append(m)
            if len(got) >= count: raise KeyboardInterrupt
        return gw, got, inbound

    def test_identify_heartbeat_then_message(self):
        gw, got, inbound = self.listen([[HELLO, "read", READY, "ping", create(2, "hello"), "read", "read"]], 1)
        with self.assertRaises(KeyboardInterrupt): self.c.listen(inbound)
        self.assertEqual(gw.seen[0]["op"], 2); self.assertEqual(gw.seen[0]["d"]["token"], "SEKRET")
        self.assertEqual(got[0].text, "hello")
        self.assertEqual((self.c.session, self.c.seq), ("S1", 2))

    def test_heartbeat_carries_the_sequence(self):
        gw = FakeGateway([[HELLO, "read", READY, "read"]]); self.c.cfg["gateway"] = gw.url
        with self.assertRaises(ConnectionError): self.c.listen(lambda m: None)
        beat = [s for s in gw.seen if s["op"] == 1][0]
        self.assertEqual(beat["d"], 1)

    def test_reconnect_resumes_with_session_and_seq(self):
        gw, got, inbound = self.listen([[HELLO, "read", READY, create(2, "one"), {"op": 7, "d": None}],
                                        [HELLO, "read", create(3, "two")]], 2)
        with self.assertRaises(KeyboardInterrupt): self.c.listen(inbound)
        self.assertEqual([m.text for m in got], ["one", "two"])
        resume = [s for s in gw.seen if s["op"] == 6][0]["d"]
        self.assertEqual((resume["session_id"], resume["seq"], resume["token"]), ("S1", 2, "SEKRET"))

    def test_invalid_session_not_resumable_identifies_again(self):
        gw, got, inbound = self.listen([[HELLO, "read", READY, {"op": 9, "d": False}],
                                        [HELLO, "read", create(4, "back")]], 1)
        with self.assertRaises(KeyboardInterrupt): self.c.listen(inbound)
        self.assertEqual([s["op"] for s in gw.seen if s["op"] in (2, 6)], [2, 2])

    def test_unacknowledged_heartbeat_drops_the_link(self):
        gw = FakeGateway([[HELLO, "read", "read", "read", "read"]]); self.c.cfg["gateway"] = gw.url
        with self.assertRaises(ConnectionError) as e: self.c.listen(lambda m: None)
        self.assertIn("heartbeat", str(e.exception))

    def test_bad_token_close_is_a_clear_error_without_the_token(self):
        gw = FakeGateway([[HELLO, "read", "close4004"]]); self.c.cfg["gateway"] = gw.url
        with self.assertRaises(RuntimeError) as e: self.c.listen(lambda m: None)
        self.assertNotIn("SEKRET", str(e.exception))

    def test_session_over_close_forgets_the_session(self):
        gw = FakeGateway([[HELLO, "read", READY, "close4007"]]); self.c.cfg["gateway"] = gw.url
        with self.assertRaises(ConnectionError): self.c.listen(lambda m: None)
        self.assertIsNone(self.c.session)

    def test_big_frame_and_split_reads(self):
        gw = FakeGateway([[HELLO, "read", READY, create(2, "x" * 70000 if False else "y" * 5000)]]); self.c.cfg["gateway"] = gw.url
        got = []
        def inbound(m): got.append(m); raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.c.listen(inbound)
        self.assertEqual(len(got[0].text), 5000)


class Whole(unittest.TestCase):
    def test_stranger_pairs_then_talks(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Rest)
        threading.Thread(target=srv.serve_forever, daemon=True).start(); Rest.calls = []
        d = Path(tempfile.mkdtemp()); board = d / "b"; board.write_text(""); posted = []
        c = D.Discord({"api": f"http://127.0.0.1:{srv.server_port}"}, "SEKRET")
        b = C.Bridge("discord", c.send, c.cfg, board, d / "s", lambda t, th, files=(), routed=False: posted.append((t, th)), lambda t: None, lambda t: "none", size=c.size, label=c.label, accepted=lambda t: True, log=lambda m: None)
        c.handle(create(1, "hello", author="7")["d"], b.inbound); b.pump()
        said = json.loads(Rest.calls[-1][2])["content"]
        self.assertEqual(posted, [])
        code = said.split("pair discord ")[1].split()[0]
        with board.open("a") as f: f.write(json.dumps({"id": "p", "from": "person", "thread": "t", "to": [], "text": f"pair discord {code}", "via": "web-pair"}) + "\n")
        b.pump()
        self.assertIn("Connected", json.loads(Rest.calls[-1][2])["content"])
        c.handle(create(2, "do it", author="7")["d"], b.inbound)
        self.assertTrue(posted[0][0].startswith("@new (from Discord) do it"))
        c.handle(create(3, "sneak", author="7", guild="g")["d"], b.inbound)
        self.assertEqual(len(posted), 1)
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
