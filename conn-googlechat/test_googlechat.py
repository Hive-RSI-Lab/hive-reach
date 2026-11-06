"""python3 -I test_googlechat.py"""
import http.server, json, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as G


class Fake(http.server.BaseHTTPRequestHandler):
    got = []
    def log_message(self, *a): pass
    def do_POST(self):
        Fake.got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        code = 403 if "bad" in self.path else 200
        self.send_response(code); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")


class T(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}/v1/spaces/S/messages?key=K&token=SECRETTOKEN"
    def tearDown(self): self.s.shutdown()

    def test_posts_text_to_the_secret_url(self):
        G.GoogleChat({}, self.url).send("space", "H2 has a message for you.")
        self.assertEqual(Fake.got, [("/v1/spaces/S/messages?key=K&token=SECRETTOKEN", {"text": "H2 has a message for you."})])

    def test_failure_does_not_show_the_url(self):
        with self.assertRaises(RuntimeError) as e: G.GoogleChat({}, self.url.replace("messages", "bad")).send("space", "x")
        self.assertNotIn("SECRETTOKEN", str(e.exception))

    def test_one_way_and_setup_pings_short(self):
        c = G.GoogleChat({}, self.url); self.assertFalse(c.can_receive); self.assertEqual(c.setup(), {"pings": "short", "home": "space"})
        self.assertEqual(G.GoogleChat({"home": "x"}, self.url).setup(), {})

    def test_ready_needs_https_webhook(self):
        self.assertEqual(G.GoogleChat({}, self.url).ready(), "")
        self.assertEqual(G.GoogleChat({}, "https://chat.googleapis.com/v1/spaces/S/messages?key=k").ready(), "")
        self.assertIn("https", G.GoogleChat({}, "http://chat.example/x").ready()); self.assertIn("webhook", G.GoogleChat({}, "").ready())


if __name__ == "__main__": unittest.main()
