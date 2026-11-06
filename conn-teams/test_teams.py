"""python3 -I test_teams.py"""
import http.server, json, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as T


class Fake(http.server.BaseHTTPRequestHandler):
    got = []
    def log_message(self, *a): pass
    def do_POST(self):
        Fake.got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        code = 400 if "bad" in self.path else 202
        self.send_response(code); self.send_header("Content-Length", "0"); self.end_headers()


class Tt(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}/workflows/abc/triggers/manual/paths/invoke?sig=SECRETSIG"
    def tearDown(self): self.s.shutdown()

    def test_posts_an_adaptive_card_envelope(self):
        T.Teams({}, self.url).send("channel", "H2 has a message for you.")
        path, body = Fake.got[0]
        self.assertTrue(path.endswith("sig=SECRETSIG")); self.assertEqual(body["type"], "message")
        att = body["attachments"][0]; self.assertEqual(att["contentType"], "application/vnd.microsoft.card.adaptive")
        self.assertEqual(att["content"]["type"], "AdaptiveCard"); self.assertEqual(att["content"]["body"][0]["text"], "H2 has a message for you.")

    def test_failure_does_not_show_the_url(self):
        with self.assertRaises(RuntimeError) as e: T.Teams({}, self.url.replace("workflows", "bad")).send("channel", "x")
        self.assertNotIn("SECRETSIG", str(e.exception))

    def test_one_way_and_setup_pings_short(self):
        c = T.Teams({}, self.url); self.assertFalse(c.can_receive); self.assertEqual(c.setup(), {"pings": "short", "home": "channel"})

    def test_ready_needs_https_webhook(self):
        self.assertEqual(T.Teams({}, self.url).ready(), "")
        self.assertIn("https", T.Teams({}, "http://x.example/y").ready()); self.assertIn("webhook", T.Teams({}, "").ready())


if __name__ == "__main__": unittest.main()
