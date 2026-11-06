"""python3 -I test_gotify.py"""
import http.server, json, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as G


class Fake(http.server.BaseHTTPRequestHandler):
    got = []
    def log_message(self, *a): pass
    def do_POST(self):
        Fake.got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))), self.headers["X-Gotify-Key"]))
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")


class T(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}"
    def tearDown(self): self.s.shutdown()

    def test_content_free_by_default(self):
        G.Gotify({"server": self.url}, "TOK").send("phone", "the secret plan")
        path, body, key = Fake.got[0]
        self.assertEqual((path, body["message"], key), ("/message", G.LINE, "TOK")); self.assertNotIn("TOK", path)

    def test_carry_words_over_http_is_still_content_free(self):
        G.Gotify({"server": self.url, "carry_words": True}, "TOK").send("phone", "the secret plan")
        self.assertEqual(Fake.got[0][1]["message"], G.LINE)

    def test_words_need_https_and_true(self):
        self.assertTrue(G.Gotify({"server": "https://g.example", "carry_words": True}, "t").carries())
        self.assertFalse(G.Gotify({"server": "https://g.example"}, "t").carries())
        self.assertFalse(G.Gotify({"server": "https://g.example", "carry_words": "yes"}, "t").carries())

    def test_https_with_words_sends_them(self):
        seen = []; real = C.http
        C.http = lambda m, u, body=None, headers=None, timeout=0, **k: seen.append((u, body, headers))
        try: G.Gotify({"server": "https://g.example/", "carry_words": True}, "TOK").send("phone", "the plan")
        finally: C.http = real
        self.assertEqual((seen[0][0], seen[0][1]["message"]), ("https://g.example/message", "the plan"))

    def test_one_way_and_setup(self):
        c = G.Gotify({"server": self.url}, "t"); self.assertFalse(c.can_receive)
        self.assertEqual(c.setup()["pings"], "short"); self.assertEqual(c.ready(), "")
        self.assertIn("server", G.Gotify({}, "t").ready())


if __name__ == "__main__": unittest.main()
