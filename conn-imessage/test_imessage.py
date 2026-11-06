"""NOT TESTED ON A MAC. This checks the filter, the chat.db parsing and the spool against a fixture sqlite DB and fakes:
python3 -I test_imessage.py. The real chat.db layout, osascript and ssh are assumptions until someone runs it on a Mac."""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import sqlite3
import conn as C
import connector as I
import spool as S
import mac_bridge as M

ME = "+46701234567"
T0 = 800_000_000   # seconds since 2001


def blob(text):
    b = text.encode()
    n = bytes([len(b)]) if len(b) < 0x80 else b"\x81" + len(b).to_bytes(2, "little")
    return b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + n + b + b"\x86\x84\x02iI"


def fixture(path):
    db = sqlite3.connect(path)
    db.executescript("""create table chat(ROWID integer primary key, chat_identifier text, style int);
      create table message(ROWID integer primary key, text text, attributedBody blob, is_from_me int, date int, cache_has_attachments int default 0, service text default 'iMessage');
      create table chat_message_join(chat_id int, message_id int);""")
    db.executemany("insert into chat values(?,?,?)", [(1, "+46701234567", 45), (2, "+46709999999", 45), (3, "chat123456", 43), (4, "+46701234567", 43)])
    rows = [  # chat, text, blob, from_me, secs after T0, attachment
        (2, "SECRET-OTHER", None, 0, 1, 0), (3, "SECRET-GROUP", None, 0, 2, 0), (4, "SECRET-GROUP-WITH-ME", None, 1, 3, 0),
        (1, "hello", None, 1, 10, 0), (1, None, blob("from a blob " + "x" * 200), 1, 20, 0), (1, "sent by hive", None, 1, 30, 0),
        (1, "sent by hive", None, 0, 31, 0), (1, "after", None, 0, 100, 0), (1, "", None, 1, 110, 1)]
    for i, (chat, text, bl, fm, secs, att) in enumerate(rows, 1):
        db.execute("insert into message(ROWID,text,attributedBody,is_from_me,date,cache_has_attachments) values(?,?,?,?,?,?)", (i, text, bl, fm, (T0 + secs) * 10**9, att))
        db.execute("insert into chat_message_join values(?,?)", (chat, i))
    db.commit(); return db


class Mac(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.path = self.tmp / "chat.db"; fixture(self.path).close()
        self.db = M.open_ro(self.path)

    def test_database_is_opened_read_only(self):
        with self.assertRaises(sqlite3.OperationalError): self.db.execute("delete from message")

    def test_an_sms_in_the_self_chat_is_not_taken(self):
        db = sqlite3.connect(self.path); db.execute("update message set service='SMS' where text='after'"); db.commit(); db.close()
        self.assertNotIn("after", [r[1] for r in M.new_rows(M.open_ro(self.path), ME, 0)])

    def test_only_the_self_chat_is_selected(self):
        self.assertEqual(M.self_chat_ids(self.db, "+46 70 123 45 67"), [1])
        rows = M.new_rows(self.db, ME, 0)
        self.assertNotIn("SECRET", repr(rows))
        self.assertEqual([r[0] for r in rows], [4, 5, 6, 7, 8, 9])
        self.assertEqual(M.self_chat_ids(self.db, "nobody@example.com"), [])

    def test_text_and_blob_and_date(self):
        rows = {r[0]: r for r in M.new_rows(self.db, ME, 0)}
        self.assertEqual(rows[5][1], "from a blob " + "x" * 200)   # long enough for the two-byte length
        self.assertEqual(rows[4][3], T0 + 10 + M.APPLE_EPOCH)
        self.assertEqual(M.body_text(None, blob("hi")), "hi"); self.assertEqual(M.body_text(None, b"junk"), "")

    def test_bridge_filters_echo_twin_and_starts_at_now(self):
        sent, osa = [], []
        b = M.Bridge(self.db, ME, self.tmp / "st.json", sent.extend, lambda: [json.dumps({"text": "sent by hive"})], lambda t, h: osa.append((t, h)))
        b.pump_in(); self.assertEqual(sent, [])   # first start: old history is not replayed
        b.state["rowid"] = 0
        b.pump_out(); self.assertEqual(osa, [("sent by hive", ME)])
        b.pump_in()
        self.assertEqual([json.loads(s)["text"] for s in sent], ["hello", "from a blob " + "x" * 200, "after", "(an attachment was sent; attachments aren't forwarded)"])
        self.assertTrue(all(json.loads(s)["handle"] == ME for s in sent))
        self.assertEqual(b.state["rowid"], 9)
        self.assertEqual(oct((self.tmp / "st.json").stat().st_mode & 0o777), "0o600")

    def test_failed_put_is_retried_not_lost(self):
        calls = []
        def put(ls):
            calls.append(ls)
            if len(calls) == 1: raise RuntimeError("down")
        b = M.Bridge(self.db, ME, self.tmp / "st.json", put, lambda: [], lambda t, h: None); b.state["rowid"] = 0
        with self.assertRaises(RuntimeError): b.pump_in()
        self.assertEqual(b.state["rowid"], 0)
        b.pump_in(); self.assertEqual(json.loads(calls[1][0])["text"], "hello")


class Tower(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); C.DATA = self.tmp / "data"
        self.c = I.IMessage({"self": ME, "spool": str(self.tmp / "spool")}); self.c.setup()

    def test_spool_keeps_only_the_self_handle(self):
        lines = [json.dumps({"id": "1", "handle": "+46709999999", "text": "SECRET"}), "not json", json.dumps({"id": "2", "handle": "+46 70 123 4567", "text": "mine"}), json.dumps([1])]
        self.assertEqual(S.put(lines, self.c.spool, ME), 1)
        files = list((self.c.spool / "in").glob("*.json"))
        self.assertEqual(len(files), 1); self.assertNotIn("SECRET", files[0].read_text())

    def test_listen_delivers_and_clears(self):
        S.put([json.dumps({"id": "2", "handle": ME, "text": "mine"})], self.c.spool, ME)
        S.write(self.c.spool, "in", {"id": "3", "handle": "+46709999999", "text": "SECRET"})   # even if one got in some other way
        got = []
        import time; real = time.sleep
        I.time.sleep = lambda s: (_ for _ in ()).throw(KeyboardInterrupt)
        try:
            with self.assertRaises(KeyboardInterrupt): self.c.listen(got.append)
        finally: I.time.sleep = real
        self.assertEqual([(m.text, m.chat, m.sender) for m in got], [("mine", ME, ME)])
        self.assertEqual(list((self.c.spool / "in").glob("*.json")), [])

    def test_own_echo_is_dropped_by_the_connector_too(self):
        self.c.send(ME, "from the hive")
        self.assertEqual(json.loads(next((self.c.spool / "out").glob("*.json")).read_text()), {"text": "from the hive"})
        echo = {"handle": ME, "text": "from the hive", "id": "9"}
        self.assertIsNone(self.c.accept(echo)); self.assertIsNone(self.c.accept(echo))
        self.assertIsNotNone(self.c.accept(echo))   # only two rows per send are explained away
        self.assertIsNotNone(self.c.accept({"handle": ME, "text": "something else"}))

    def test_take_hands_over_and_removes(self):
        self.c.send(ME, "a")
        self.assertEqual(S.take(self.c.spool), [{"text": "a"}]); self.assertEqual(S.take(self.c.spool), [])

    def test_send_elsewhere_refused_and_flags(self):
        with self.assertRaises(PermissionError): self.c.send("+46709999999", "x")
        self.assertEqual(list((self.c.spool / "out").glob("*.json")), [])
        self.assertEqual(self.c.setup(), {"allow": [ME], "home": ME})
        self.assertEqual(self.c.ready(), "")
        self.assertIn("handle", I.IMessage({}).ready())
        self.assertTrue(I.IMessage.self_chat_only); self.assertEqual(I.IMessage.kind, "linked")
        self.assertEqual(json.loads((Path(__file__).parent / "module.json").read_text())["kind"], "linked")


if __name__ == "__main__":
    unittest.main()
