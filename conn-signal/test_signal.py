"""Against a fake signal-cli script (no Java, no network): python3 -I test_signal.py"""
import json, os, stat, sys, tempfile, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as S
import link

ME = "+10000000001"
FAKE = Path(__file__).resolve().parent / "fake_signal_cli.py"


def make(tmp):
    session = Path(tmp) / "session"; session.mkdir(mode=0o700); (session / "data").write_text("x"); session.chmod(0o700)
    os.environ["FAKE_LOG"] = str(Path(tmp) / "calls.log")
    return S.Signal({"self": ME, "session": str(session), "cmd": [sys.executable, "-I", str(FAKE)]})


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); C.DATA = Path(self.tmp) / "data"
        self.c = make(self.tmp); self.got = []; self.done = threading.Event()
        def inbound(m):
            self.got.append(m)
            if m.text.startswith("echo-check"): self.done.set()
        self.t = threading.Thread(target=self.run_listen, args=(inbound,), daemon=True); self.t.start()
        for _ in range(100):
            if self.c.proc and self.got: break
            time.sleep(0.05)

    def run_listen(self, inbound):
        try: self.c.listen(inbound)
        except RuntimeError: pass  # killed at teardown

    def tearDown(self):
        if self.c.proc: self.c.proc.kill()

    def calls(self): return (Path(self.tmp) / "calls.log").read_text() if (Path(self.tmp) / "calls.log").exists() else ""

    def test_only_note_to_self_gets_through(self):
        time.sleep(0.3)
        self.assertEqual([m.text for m in self.got], ["note to self"])
        m = self.got[0]
        self.assertEqual((m.chat, m.sender, m.dm), (ME, ME, True))
        self.assertEqual(m.files[0].read_bytes(), b"hello"); self.assertNotIn("..", m.files[0].name)

    def test_nothing_of_other_chats_is_fetched_or_kept(self):
        time.sleep(0.3)
        self.assertNotIn("otherfile", self.calls())
        self.assertEqual(self.calls().count("getAttachment"), 1)
        self.assertNotIn("SECRET", repr(self.got))

    def test_own_echo_is_dropped(self):
        for text in ("hello from the hive", "race"):
            self.c.send(ME, text)
        time.sleep(0.5)
        self.assertEqual([m.text for m in self.got], ["note to self"])  # neither send came back as a message
        self.assertEqual(self.calls().count('"send"'), 2)
        self.assertTrue(json.loads(self.calls().splitlines()[-1])[1]["noteToSelf"])

    def test_a_new_message_after_an_echo_still_arrives(self):
        self.c.send(ME, "x")
        self.c.q.put(({"timestamp": 5000, "message": "from the person"}, {}))
        time.sleep(1.2)
        self.assertEqual([m.text for m in self.got][-1], "from the person")

    def test_send_to_anyone_else_is_refused_in_code(self):
        with self.assertRaises(PermissionError): self.c.send("+10000000002", "hi")
        self.assertNotIn('"send"', self.calls())

    def test_filter_pure(self):
        env = lambda **sm: {"sourceNumber": ME, "syncMessage": {"sentMessage": sm}}
        self.assertIsNotNone(S.self_note(env(destinationNumber="+1 000 000 0001"), ME))
        self.assertIsNone(S.self_note(env(destinationNumber="+10000000002"), ME))
        self.assertIsNone(S.self_note(env(), ME))
        self.assertIsNone(S.self_note({"sourceNumber": "+10000000002", "syncMessage": {"sentMessage": {"destinationNumber": ME}}}, ME))
        self.assertIsNone(S.self_note({"dataMessage": {"message": "x"}}, ME))
        self.assertIsNone(S.self_note(env(destinationNumber=ME), ""))

    def test_setup_trusts_the_person_and_ready_checks_session(self):
        self.assertEqual(self.c.setup(), {"allow": [ME], "home": ME})
        self.assertEqual(self.c.ready(), "")
        self.c.session.chmod(0o755); self.assertIn("chmod 700", self.c.ready()); self.c.session.chmod(0o700)
        self.assertIn("number", S.Signal({}).ready())
        self.assertIn("not linked", S.Signal({"self": ME, "session": self.tmp + "/none", "cmd": [sys.executable]}).ready())

    def test_class_flags(self):
        self.assertTrue(S.Signal.self_chat_only); self.assertEqual(S.Signal.kind, "linked")
        self.assertEqual(json.loads((Path(__file__).parent / "module.json").read_text())["kind"], "linked")

    def test_link_picks_the_plain_release(self):
        rel = {"tag_name": "v0.13.9", "assets": [{"name": "signal-cli-0.13.9.tar.gz.asc"}, {"name": "signal-cli-0.13.9-Linux-native.tar.gz"}, {"name": "signal-cli-0.13.9.tar.gz"}]}
        self.assertEqual(link.pick_asset(rel)["name"], "signal-cli-0.13.9.tar.gz")


if __name__ == "__main__":
    unittest.main()
