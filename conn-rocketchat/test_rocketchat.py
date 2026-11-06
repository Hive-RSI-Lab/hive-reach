"""Against a fake Rocket.Chat on loopback: python3 -I test_rocketchat.py"""
import http.server, json, sys, threading, unittest, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as R

SECRET = json.dumps({"user_id": "BOTID", "token": "TOKEN"})


def m(i, ts, uid, text, t=None):
    d = {"_id": i, "ts": ts, "u": {"_id": uid, "username": "name" + uid}, "msg": text}
    if t: d["t"] = t
    return d


class Fake(http.server.BaseHTTPRequestHandler):
    rooms, msgs, sent, hdrs, asked = [], {}, [], [], []
    def log_message(self, *a): pass
    def out(self, obj, code=200):
        d = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query); Fake.hdrs.append((self.headers["X-User-Id"], self.headers["X-Auth-Token"]))
        if u.path == "/api/v1/im.list": return self.out({"success": True, "ims": Fake.rooms})
        if u.path == "/api/v1/im.messages":
            Fake.asked.append(q.get("oldest"))
            old = q.get("oldest", [""])[0]
            return self.out({"success": True, "messages": [x for x in Fake.msgs[q["roomId"][0]] if x["ts"] > old]})
        self.out({"success": False, "error": "bad TOKEN"}, 400)
    def do_POST(self):
        Fake.sent.append(json.loads(self.rfile.read(int(self.headers["Content-Length"])))); self.out({"success": True})


class T(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.rooms = [{"_id": "r1", "usernames": ["bot", "al"], "lm": "2026-01-01T00:00:01Z"}, {"_id": "r2", "usernames": ["bot", "al", "bo"], "lm": "2026-01-01T00:00:01Z"}]
        Fake.msgs = {"r1": [m("old", "2026-01-01T00:00:01Z", "U1", "before we started")], "r2": [m("o2", "2026-01-01T00:00:01Z", "U1", "old")]}
        Fake.sent, Fake.hdrs, Fake.asked = [], [], []
        self.c = R.RocketChat({"server": f"http://127.0.0.1:{self.srv.server_port}"}, SECRET)
    def tearDown(self): self.srv.shutdown()

    def test_polls_new_dm_messages_by_user_id(self):
        got = []; self.c.poll_once(got.append, first=True); self.assertEqual(got, [])
        Fake.msgs["r1"] += [m("a", "2026-01-01T00:00:05Z", "U1", "hello"), m("b", "2026-01-01T00:00:06Z", "BOTID", "mine"),
                            m("c", "2026-01-01T00:00:07Z", "U1", "joined", t="uj"), m("d", "2026-01-01T00:00:08Z", "U2", "from someone else")]
        Fake.msgs["r2"] += [m("e", "2026-01-01T00:00:09Z", "U1", "group talk")]
        self.c.poll_once(got.append); self.c.poll_once(got.append)
        self.assertEqual([(x.sender, x.chat, x.dm, x.text) for x in got], [("U1", "r1", True, "hello"), ("U2", "r1", True, "from someone else"), ("U1", "r2", False, "group talk")])
        self.assertEqual(set(Fake.hdrs), {("BOTID", "TOKEN")})

    def test_new_room_after_start_is_read_from_the_beginning(self):
        self.c.poll_once(lambda x: None, first=True)
        Fake.rooms.append({"_id": "r3", "usernames": ["bot", "cy"], "lm": "2026-01-01T00:00:02Z"})
        Fake.msgs["r3"] = [m("n", "2026-01-01T00:00:02Z", "U3", "first words")]
        got = []; self.c.poll_once(got.append); self.assertEqual([x.text for x in got], ["first words"])

    def test_send(self):
        self.c.send("r1", "yo"); self.assertEqual(Fake.sent, [{"roomId": "r1", "text": "yo"}])

    def test_errors_hide_token(self):
        Fake.rooms = None
        with self.assertRaises(RuntimeError) as e: self.c.call("GET", "/nothing")
        self.assertNotIn("TOKEN", str(e.exception)); self.assertIn("***", str(e.exception))

    def test_ready(self):
        self.assertIn("server", R.RocketChat({}, SECRET).ready()); self.assertIn("login", R.RocketChat({"server": "s"}, "garbage").ready())
        self.assertIn("login", R.RocketChat({"server": "s"}, '{"token": "t"}').ready()); self.assertEqual(self.c.ready(), "")


if __name__ == "__main__": unittest.main()
