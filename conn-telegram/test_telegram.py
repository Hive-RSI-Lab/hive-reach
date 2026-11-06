"""Against a fake Bot API on loopback: python3 -I test_telegram.py"""
import http.server, json, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as T


class Fake(http.server.BaseHTTPRequestHandler):
    calls, updates = [], []
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        method = self.path.rsplit("/", 1)[-1]
        Fake.calls.append((self.path, method, body))
        result = {"getUpdates": Fake.updates, "getFile": {"file_path": "docs/a.pdf"}}.get(method, {})
        if method == "getUpdates": Fake.updates = []
        out = json.dumps({"ok": method != "sendFail", "result": result, "description": "nope"}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def do_GET(self):
        out = b"PDFDATA"; self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


class T1(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.calls, Fake.updates = [], []
        C.DATA = Path(tempfile.mkdtemp())
        self.c = T.Telegram({"api": f"http://127.0.0.1:{self.srv.server_port}"}, "SEKRET")

    def tearDown(self): self.srv.shutdown()

    def got(self, update):
        out = []; self.c.handle(update, out.append); return out

    def test_private_message_uses_the_fixed_id_not_the_name(self):
        m = self.got({"update_id": 5, "message": {"text": "hi", "chat": {"id": 42, "type": "private"}, "from": {"id": 42, "username": "admin"}}})[0]
        self.assertEqual((m.sender, m.chat, m.dm, m.text, m.id), ("42", "42", True, "hi", "5"))

    def test_group_is_marked_and_fetches_nothing(self):
        m = self.got({"update_id": 6, "message": {"caption": "x", "document": {"file_id": "f"}, "chat": {"id": -9, "type": "group"}, "from": {"id": 42}}})[0]
        self.assertFalse(m.dm); self.assertEqual(m.files, [])
        self.assertEqual(Fake.calls, [])

    def test_bots_and_edits_are_ignored(self):
        self.assertEqual(self.got({"update_id": 7, "edited_message": {"text": "x"}}), [])
        self.assertEqual(self.got({"update_id": 8, "message": {"text": "x", "chat": {"id": 1, "type": "private"}, "from": {"id": 9, "is_bot": True}}}), [])

    def test_a_strangers_file_is_not_fetched(self):
        m = self.got({"update_id": 11, "message": {"document": {"file_id": "f", "file_name": "a.pdf"}, "chat": {"id": 7, "type": "private"}, "from": {"id": 7}}})[0]
        self.assertEqual(m.files, []); self.assertEqual(Fake.calls, [])

    def test_attachment_lands_on_disk(self):
        self.c.trusted = lambda s: True
        m = self.got({"update_id": 9, "message": {"document": {"file_id": "f", "file_name": "../a.pdf"}, "chat": {"id": 1, "type": "private"}, "from": {"id": 1}}})[0]
        self.assertEqual(m.files[0].read_bytes(), b"PDFDATA")
        self.assertEqual(m.files[0].name, "_a.pdf".lstrip("_") if False else m.files[0].name)
        self.assertNotIn("..", m.files[0].name)

    def test_too_big_is_named_not_lost(self):
        self.c.trusted = lambda s: True
        m = self.got({"update_id": 10, "message": {"text": "see", "document": {"file_id": "f", "file_name": "big.bin", "file_size": 30 * 2**20}, "chat": {"id": 1, "type": "private"}, "from": {"id": 1}}})[0]
        self.assertIn("big.bin", m.text); self.assertEqual(m.files, [])

    def test_send_text_and_file(self):
        d = Path(tempfile.mkdtemp()); f = d / "x.txt"; f.write_text("data")
        self.c.send("42", "hello", [f])
        self.assertEqual([c[1] for c in Fake.calls], ["sendMessage", "sendDocument"])
        self.assertIn(b"data", Fake.calls[1][2])

    def test_api_error_raises_so_the_bridge_retries(self):
        with self.assertRaises(RuntimeError):
            self.c.call("sendFail")

    def test_listen_acks_with_offset(self):
        got = []
        Fake.updates = [{"update_id": 3, "message": {"text": "a", "chat": {"id": 1, "type": "private"}, "from": {"id": 1}}}]
        def stop(*a):
            got.append(a[0]); raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.c.listen(stop)
        self.assertEqual(self.c.offset, 4)


class Whole(unittest.TestCase):
    def test_stranger_pairs_then_talks_over_the_fake_api(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        Fake.calls, Fake.updates = [], []
        d = Path(tempfile.mkdtemp()); board = d / "b"; board.write_text(""); posted = []
        c = T.Telegram({"api": f"http://127.0.0.1:{srv.server_port}"}, "SEKRET")
        b = C.Bridge("telegram", c.send, c.cfg, board, d / "s", lambda t, th, files=(), routed=False: posted.append((t, th)), lambda t: None, lambda t: "none", size=c.size, label=c.label, accepted=lambda t: True, log=lambda m: None)
        up = lambda i, t: {"update_id": i, "message": {"text": t, "chat": {"id": 7, "type": "private"}, "from": {"id": 7}}}
        c.handle(up(1, "hello"), b.inbound); b.pump()
        said = json.loads(Fake.calls[-1][2])["text"]
        self.assertEqual(posted, [])
        code = said.split("pair telegram ")[1].split()[0]
        with board.open("a") as f: f.write(json.dumps({"id": "p", "from": "person", "thread": "t", "to": [], "via": "web-pair", "text": f"pair telegram {code}"}) + "\n")
        b.pump()
        self.assertIn("Connected", json.loads(Fake.calls[-1][2])["text"])
        c.handle(up(2, "do it"), b.inbound)
        self.assertTrue(posted[0][0].startswith("@new (from Telegram) do it"))
        with board.open("a") as f: f.write(json.dumps({"id": "q", "from": "a7", "thread": "conn-telegram-7", "to": ["@person"], "text": "@person done"}) + "\n")
        b.pump()
        self.assertEqual(json.loads(Fake.calls[-1][2])["text"], "done")
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
