"""python3 -I test_ntfy.py"""
import http.server, sys, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import connector as N


class Fake(http.server.BaseHTTPRequestHandler):
    got = []
    def log_message(self, *a): pass
    def do_POST(self):
        Fake.got.append((self.path, self.rfile.read(int(self.headers.get("Content-Length") or 0)), dict(self.headers)))
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()


class Tn(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}"
    def tearDown(self): self.s.shutdown()

    def test_public_server_never_gets_the_words(self):
        real = N.C_SERVER; N.C_SERVER = self.url
        try: N.Ntfy({"topic": "t", "server": self.url}, "").send("phone", "the secret plan")
        finally: N.C_SERVER = real
        self.assertEqual(Fake.got[0][1], N.LINE.encode())

    def test_a_token_alone_does_not_unlock_the_public_server(self):
        real = N.C_SERVER; N.C_SERVER = self.url
        try: N.Ntfy({"topic": "t", "server": self.url}, "tok").send("phone", "the secret plan")
        finally: N.C_SERVER = real
        self.assertEqual(Fake.got[0][1], N.LINE.encode())
        self.assertNotIn("Authorization", Fake.got[0][2])

    def test_own_server_with_token_carries_words(self):
        N.Ntfy({"topic": "t", "server": self.url}, "tok").send("phone", "the plan")
        self.assertEqual(Fake.got[0][1], b"the plan")
        self.assertEqual(Fake.got[0][2]["Authorization"], "Bearer tok")

    def test_setup_makes_a_long_topic_once(self):
        c = N.Ntfy({}, ""); self.assertTrue(c.ready())
        ch = c.setup(); self.assertGreater(len(ch["topic"]), 20); self.assertEqual(ch["pings"], "short")
        self.assertEqual(N.Ntfy({"topic": "x"}, "").setup(), {})
        self.assertFalse(N.Ntfy({"topic": "x"}, "").can_receive)


if __name__ == "__main__":
    unittest.main()
