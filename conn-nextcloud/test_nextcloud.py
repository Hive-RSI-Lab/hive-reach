"""Against a fake Nextcloud Talk on loopback: python3 -I test_nextcloud.py"""
import base64, http.server, json, sys, threading, unittest, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as N


def msg(i, actor, text, typ="users", **kw):
    return {"id": i, "actorType": typ, "actorId": actor, "message": text, "messageType": "comment", "systemMessage": "", "actorDisplayName": "D"} | kw


class Fake(http.server.BaseHTTPRequestHandler):
    rooms, msgs, sent, auth, asked = [], {}, [], [], []
    def log_message(self, *a): pass
    def out(self, data, code=200):
        d = json.dumps({"ocs": {"meta": {}, "data": data}}).encode(); self.send_response(code); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
        Fake.auth.append((self.headers["Authorization"], self.headers["OCS-APIRequest"]))
        if u.path.endswith("/v4/room"): return self.out(Fake.rooms)
        tok = u.path.rsplit("/", 1)[-1]; Fake.asked.append(tok)
        new = [x for x in Fake.msgs.get(tok, []) if x["id"] > int(q["lastKnownMessageId"][0])]
        if not new: self.send_response(304); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.out(new)
    def do_POST(self):
        Fake.sent.append((self.path.rsplit("/", 1)[-1], json.loads(self.rfile.read(int(self.headers["Content-Length"]))))); self.out({})


class T(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.rooms = [{"token": "one", "type": 1, "lastMessage": {"id": 3}}, {"token": "grp", "type": 2, "lastMessage": {"id": 1}}]
        Fake.msgs = {"one": [msg(3, "al", "old")], "grp": [msg(1, "al", "group chatter")]}
        Fake.sent, Fake.auth, Fake.asked = [], [], []
        self.c = N.Nextcloud({"server": f"http://127.0.0.1:{self.srv.server_port}", "user": "bot"}, "APPPW")
    def tearDown(self): self.srv.shutdown()

    def test_only_one_to_one_rooms_and_user_actors(self):
        got = []; self.c.poll_once(got.append, first=True); self.assertEqual(got, [])
        Fake.msgs["one"] += [msg(4, "al", "hi"), msg(5, "bot", "mine"), msg(6, "guest-xyz", "hello", typ="guests"), msg(7, "al", "joined", systemMessage="user_added"),
                             msg(8, "bo", "again"), msg(9, "bridge", "bot post", typ="bots")]
        Fake.msgs["grp"] += [msg(2, "al", "more group")]
        self.c.poll_once(got.append); self.c.poll_once(got.append)
        self.assertEqual([(m.sender, m.chat, m.dm, m.text) for m in got], [("al", "one", True, "hi"), ("bo", "one", True, "again")])
        self.assertNotIn("grp", Fake.asked)
        self.assertEqual(set(Fake.auth), {("Basic " + base64.b64encode(b"bot:APPPW").decode(), "true")})

    def test_send(self):
        self.c.send("one", "yo"); self.assertEqual(Fake.sent, [("one", {"message": "yo"})])

    def test_ready(self):
        self.assertIn("server", N.Nextcloud({}, "p").ready()); self.assertIn("app password", N.Nextcloud({"server": "s", "user": "u"}, "").ready())
        self.assertEqual(self.c.ready(), "")


if __name__ == "__main__": unittest.main()
