"""Against a fake homeserver on loopback: python3 -I test_matrix.py"""
import http.server, json, sys, tempfile, threading, unittest, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as M

ME = "@bot:hs"


class Fake(http.server.BaseHTTPRequestHandler):
    calls, syncs, members = [], [], {}
    def log_message(self, *a): pass
    def reply(self, obj, code=200):
        out = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def handle_any(self):
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n)
        path = urllib.parse.unquote(self.path)
        Fake.calls.append((self.command, path, dict(self.headers), body))
        if self.headers.get("Authorization") != "Bearer SEKRET": return self.reply({"errcode": "M_UNKNOWN_TOKEN"}, 401)
        if "/account/whoami" in path: return self.reply({"user_id": ME})
        if "/joined_members" in path:
            room = path.split("/rooms/")[1].split("/")[0]
            return self.reply({"joined": {m: {} for m in Fake.members.get(room, [])}})
        if "/sync" in path: return self.reply(Fake.syncs.pop(0) if Fake.syncs else {"next_batch": "end"})
        if "/media/v3/upload" in path: return self.reply({"content_uri": "mxc://hs/up1"})
        if "/client/v1/media/download" in path: return self.reply({"errcode": "M_UNRECOGNIZED"}, 404)
        if "/media/v3/download" in path: return self.reply(b"PDFDATA")
        self.reply({"event_id": "$sent"})
    do_GET = do_PUT = do_POST = handle_any


def msg(room, who, text, eid="$e1", mt="m.text", **extra):
    return {"type": "m.room.message", "sender": who, "event_id": eid, "content": {"msgtype": mt, "body": text, **extra}}

def sync(room_events=None, invite=None, nb="s2"):
    return {"next_batch": nb, "rooms": {"join": {r: {"timeline": {"events": e}} for r, e in (room_events or {}).items()}, "invite": invite or {}}}


class T1(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        Fake.calls, Fake.syncs, Fake.members = [], [], {"!dm:hs": ["@alice:hs", ME], "!grp:hs": ["@alice:hs", ME, "@bob:hs"]}
        C.DATA = Path(tempfile.mkdtemp())
        self.c = M.Matrix({"server": f"http://127.0.0.1:{self.srv.server_port}"}, "SEKRET"); self.c.me = ME

    def tearDown(self): self.srv.shutdown()

    def got(self, room, ev):
        out = []; self.c.handle(room, ev, out.append); return out

    def sent(self): return [c for c in Fake.calls if c[0] == "PUT"]

    def test_two_member_room_is_a_dm_and_sender_is_the_mxid(self):
        m = self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "hi"))[0]
        self.assertEqual((m.sender, m.chat, m.dm, m.text, m.id), ("@alice:hs", "!dm:hs", True, "hi", "$e1"))

    def test_bigger_room_is_not_a_dm_and_fetches_nothing(self):
        m = self.got("!grp:hs", msg("!grp:hs", "@alice:hs", "x", mt="m.file", url="mxc://hs/f"))[0]
        self.assertFalse(m.dm); self.assertEqual(m.files, [])
        self.assertFalse([c for c in Fake.calls if "download" in c[1]])

    def test_sender_who_is_not_a_member_is_not_a_dm(self):
        self.assertFalse(self.got("!dm:hs", msg("!dm:hs", "@mallory:hs", "x"))[0].dm)

    def test_own_notices_edits_and_other_types_ignored(self):
        self.assertEqual(self.got("!dm:hs", msg("!dm:hs", ME, "x")), [])
        self.assertEqual(self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "x", mt="m.notice")), [])
        self.assertEqual(self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "x", **{"m.relates_to": {"rel_type": "m.replace"}})), [])
        self.assertEqual(self.got("!dm:hs", {"type": "m.reaction", "sender": "@alice:hs", "content": {}}), [])

    def test_a_strangers_file_is_not_fetched(self):
        self.assertEqual(self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "a.pdf", mt="m.file", url="mxc://hs/abc"))[0].files, [])
        self.assertFalse([c for c in Fake.calls if "download" in c[1]])

    def test_attachment_lands_on_disk_falling_back_to_the_old_media_path(self):
        self.c.trusted = lambda s: True
        m = self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "../a.pdf", mt="m.file", url="mxc://hs/abc"))[0]
        self.assertEqual(m.files[0].read_bytes(), b"PDFDATA"); self.assertNotIn("..", m.files[0].name)
        self.assertEqual(m.text, "")

    def test_too_big_is_named_not_lost(self):
        self.c.trusted = lambda s: True
        m = self.got("!dm:hs", msg("!dm:hs", "@alice:hs", "big.bin", mt="m.file", url="mxc://hs/b", info={"size": 30 * 2**20}))[0]
        self.assertIn("big.bin", m.text); self.assertEqual(m.files, [])

    def test_send_text_and_file(self):
        f = Path(tempfile.mkdtemp()) / "x.txt"; f.write_text("data")
        self.c.send("!dm:hs", "hello", [f])
        puts = self.sent()
        self.assertEqual(json.loads(puts[0][3]), {"msgtype": "m.text", "body": "hello"})
        self.assertIn("/rooms/!dm:hs/send/m.room.message/", puts[0][1])
        self.assertEqual(json.loads(puts[1][3])["url"], "mxc://hs/up1")
        self.assertTrue([c for c in Fake.calls if c[0] == "POST" and c[3] == b"data"])

    def test_wrong_token_raises_without_the_token(self):
        self.c.secret = "BAD"
        with self.assertRaises(RuntimeError) as e: self.c.send("!dm:hs", "x")
        self.assertNotIn("BAD", str(e.exception))

    def test_encrypted_event_answered_once_per_private_room(self):
        enc = {"type": "m.room.encrypted", "sender": "@alice:hs", "content": {}}
        self.got("!dm:hs", enc); self.assertEqual(self.sent(), [])  # a stranger: not a word
        self.c.cfg["allow"] = ["@alice:hs"]
        self.assertEqual(self.got("!dm:hs", enc), []); self.got("!dm:hs", enc)
        self.assertEqual(len(self.sent()), 1)
        self.assertIn("encrypted", json.loads(self.sent()[0][3])["body"])
        self.c.__init__(self.c.cfg, "SEKRET")  # a restart: still told only once
        self.got("!dm:hs", enc); self.assertEqual(len(self.sent()), 1)

    def test_encrypted_event_in_a_group_gets_no_answer(self):
        self.got("!grp:hs", {"type": "m.room.encrypted", "sender": "@alice:hs", "content": {}})
        self.assertEqual(self.sent(), [])

    def test_invite_joined_only_when_flagged_direct(self):
        inv = lambda direct: {"invite_state": {"events": [{"type": "m.room.member", "state_key": ME, "sender": "@x:hs", "content": {"membership": "invite", "is_direct": direct}}]}}
        self.c.invites({"!yes:hs": inv(True), "!no:hs": inv(False), "!none:hs": {}})
        joins = [c[1] for c in Fake.calls if "/join/" in c[1]]
        self.assertEqual(joins, ["/_matrix/client/v3/join/!yes:hs"])

    def test_listen_first_sync_skips_history_then_saves_since(self):
        Fake.syncs = [sync({"!dm:hs": [msg("!dm:hs", "@alice:hs", "old")]}, nb="s1"),
                      sync({"!dm:hs": [msg("!dm:hs", "@alice:hs", "new", eid="$n")]}, nb="s2")]
        got = []
        def stop(m): got.append(m); raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.c.listen(stop)
        self.assertEqual([m.text for m in got], ["new"])
        syncs = [c[1] for c in Fake.calls if "/sync" in c[1]]
        self.assertNotIn("since=", syncs[0]); self.assertIn("since=s1", syncs[1])
        self.assertEqual((C.DATA / "matrix" / "since").read_text(), "s1")  # s2 not saved: it wasn't finished

    def test_listen_resumes_from_the_saved_since(self):
        (C.DATA / "matrix").mkdir(parents=True); (C.DATA / "matrix" / "since").write_text("saved")
        Fake.syncs = [sync({"!dm:hs": [msg("!dm:hs", "@alice:hs", "while down")]})]
        def stop(m): raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.c.listen(stop)
        self.assertIn("since=saved", [c[1] for c in Fake.calls if "/sync" in c[1]][0])

    def test_whoami_learns_our_own_id_so_we_ignore_ourselves(self):
        self.c.me = ""
        Fake.syncs = [sync(nb="s1"), sync({"!dm:hs": [msg("!dm:hs", ME, "me"), msg("!dm:hs", "@alice:hs", "you", eid="$y")]})]
        got = []
        def stop(m): got.append(m); raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.c.listen(stop)
        self.assertEqual([m.text for m in got], ["you"])

    def test_ready_needs_server_and_token(self):
        self.assertEqual(M.Matrix({"server": "https://x"}, "t").ready(), ""); self.assertIn("https", M.Matrix({"server": "http://x"}, "t").ready()); self.assertEqual(M.Matrix({"server": "http://x", "allow_http": True}, "t").ready(), "")
        self.assertIn("homeserver", M.Matrix({}, "t").ready())
        self.assertIn("token", M.Matrix({"server": "https://x"}, "").ready())


class Whole(unittest.TestCase):
    def test_stranger_pairs_then_talks_and_group_is_dropped(self):
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        Fake.calls, Fake.members = [], {"!dm:hs": ["@alice:hs", ME], "!grp:hs": ["@alice:hs", ME, "@bob:hs"]}
        C.DATA = Path(tempfile.mkdtemp())
        d = Path(tempfile.mkdtemp()); board = d / "b"; board.write_text(""); posted = []
        c = M.Matrix({"server": f"http://127.0.0.1:{srv.server_port}"}, "SEKRET"); c.me = ME
        b = C.Bridge("matrix", c.send, c.cfg, board, d / "s", lambda t, th, files=(), routed=False: posted.append((t, th)), lambda t: None, lambda t: "none", size=c.size, label=c.label, accepted=lambda t: True, log=lambda m: None)
        say = lambda: json.loads([x for x in Fake.calls if x[0] == "PUT"][-1][3])["body"]
        c.handle("!dm:hs", msg("!dm:hs", "@alice:hs", "hello"), b.inbound); b.pump()
        self.assertEqual(posted, [])
        code = say().split("pair matrix ")[1].split()[0]
        with board.open("a") as f: f.write(json.dumps({"id": "p", "from": "person", "thread": "t", "to": [], "text": f"pair matrix {code}", "via": "web-pair"}) + "\n")
        b.pump()
        self.assertIn("Connected", say())
        c.handle("!dm:hs", msg("!dm:hs", "@alice:hs", "do it", eid="$2"), b.inbound)
        self.assertTrue(posted[0][0].startswith("@new (from Matrix) do it"))
        c.handle("!grp:hs", msg("!grp:hs", "@alice:hs", "sneak", eid="$3"), b.inbound)
        self.assertEqual(len(posted), 1)
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
