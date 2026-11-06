"""Against a fake Zulip on loopback: python3 -I test_zulip.py"""
import base64, http.server, json, sys, threading, unittest, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as Z


def msg(i, sid, text, typ="private", to=(7, 5)):
    return {"id": i, "type": "message", "message": {"id": i, "type": typ, "sender_id": sid, "content": text, "sender_full_name": "N",
            "display_recipient": [{"id": x} for x in to]}}


class Fake(http.server.BaseHTTPRequestHandler):
    polls, sent, auth = [], [], []
    def log_message(self, *a): pass
    def out(self, obj, code=200):
        d = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        Fake.auth.append(self.headers["Authorization"]); u = urllib.parse.urlsplit(self.path)
        if u.path == "/api/v1/users/me": return self.out({"result": "success", "user_id": 5})
        if u.path == "/api/v1/events":
            q = urllib.parse.parse_qs(u.query); assert q["queue_id"] == ["Q"]
            if not Fake.polls: return self.out({"result": "error", "msg": "BAD_EVENT_QUEUE_ID"}, 400)
            return self.out({"result": "success", "events": Fake.polls.pop(0)})
    def do_POST(self):
        Fake.auth.append(self.headers["Authorization"]); form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        if self.path == "/api/v1/register": return self.out({"result": "success", "queue_id": "Q", "last_event_id": -1})
        Fake.sent.append(form); self.out({"result": "success"})


class T(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.polls, Fake.sent, Fake.auth = [], [], []
        self.c = Z.Zulip({"server": f"http://127.0.0.1:{self.srv.server_port}", "email": "bot@z.example"}, "KEY")
    def tearDown(self): self.srv.shutdown()

    def test_private_only_by_sender_id(self):
        Fake.polls = [[{"id": 0, "type": "heartbeat"}, msg(1, 9, "hi"), msg(2, 9, "stream msg", "stream"), msg(3, 5, "mine"), msg(4, 9, "group", to=(5, 9, 11))],
                      [msg(5, 8, "again")]]
        got = []
        with self.assertRaises(RuntimeError): self.c.listen(got.append)  # the fake ends the queue
        self.assertEqual([(m.sender, m.chat, m.dm, m.text) for m in got], [("9", "9", True, "hi"), ("9", "9", False, "group"), ("8", "8", True, "again")])
        want = "Basic " + base64.b64encode(b"bot@z.example:KEY").decode()
        self.assertEqual(set(Fake.auth), {want})

    def test_send_private_by_id(self):
        self.c.send("9", "hello there")
        self.assertEqual(Fake.sent, [{"type": ["private"], "to": ["[9]"], "content": ["hello there"]}])

    def test_error_is_plain_and_has_no_key(self):
        with self.assertRaises(RuntimeError) as e: self.c.call("GET", "/events", {"queue_id": "Q", "last_event_id": 0})
        self.assertNotIn("KEY", str(e.exception))

    def test_ready(self):
        self.assertIn("server", Z.Zulip({}, "k").ready()); self.assertIn("API key", Z.Zulip({"server": "s", "email": "e"}, "").ready())
        self.assertEqual(self.c.ready(), "")


if __name__ == "__main__": unittest.main()
