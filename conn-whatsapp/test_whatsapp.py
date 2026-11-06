"""Against a fake bridge script (no Baileys, no network): python3 -I test_whatsapp.py"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as W

HERE = Path(__file__).resolve().parent
ME = "46701234567"


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); C.DATA = self.tmp / "data"
        s = self.tmp / "session"; s.mkdir(mode=0o700); (s / "creds.json").write_text("{}"); s.chmod(0o700)
        os.environ["FAKE_LOG"] = str(self.tmp / "sent.log")
        self.c = W.WhatsApp({"self": ME, "session": str(s), "cmd": [sys.executable, "-I", str(HERE / "fake_bridge.py")]})
        self.got = []
        threading.Thread(target=self.run_listen, daemon=True).start()
        for _ in range(100):
            if len(self.got) >= 2: break
            time.sleep(0.05)

    def run_listen(self):
        try: self.c.listen(self.got.append)
        except RuntimeError: pass

    def tearDown(self):
        if self.c.proc: self.c.proc.kill()

    def test_only_the_self_chat_gets_through(self):
        self.assertEqual([m.text for m in self.got], ["note to self", "via lid"])  # phone form and lid form
        self.assertEqual({(m.chat, m.sender, m.dm) for m in self.got}, {(ME, ME, True)})
        self.assertNotIn("SECRET", repr(self.got))

    def test_files_only_from_our_own_inbox(self):
        self.assertEqual([f.name for f in self.got[0].files], ["doc.txt"])

    def test_own_echo_is_dropped_and_the_next_message_still_arrives(self):
        self.c.send(ME, "from the hive")
        time.sleep(0.5)
        self.assertEqual([m.text for m in self.got][2:], ["after echo"])
        sent = json.loads((self.tmp / "sent.log").read_text())
        self.assertTrue(W.is_own_echo(sent["id"])); self.assertEqual(sent["text"], "from the hive")

    def test_send_elsewhere_refused_in_code(self):
        with self.assertRaises(PermissionError): self.c.send("46709999999@s.whatsapp.net", "hi")
        self.assertFalse((self.tmp / "sent.log").exists())

    def test_filter_pure(self):
        own = W.self_jids(ME, "99887766@lid")
        for j in ("46701234567@s.whatsapp.net", "46701234567:9@s.whatsapp.net", "99887766@lid"): self.assertTrue(W.is_self_chat(j, own), j)
        for j in ("46709999999@s.whatsapp.net", "1@g.us", "status@broadcast", "", None, "46701234567", "46701234567@g.us"): self.assertFalse(W.is_self_chat(j, own), j)
        self.assertIsNone(self.c.accept({"t": "msg", "id": "H2AB", "chat": f"{ME}@s.whatsapp.net", "text": "echo"}))
        self.assertIsNone(self.c.accept({"t": "msg", "id": "9", "chat": "1@g.us", "text": "x"}))

    def test_setup_ready_flags(self):
        self.assertEqual(self.c.setup(), {"allow": [ME], "home": ME})
        self.assertEqual(self.c.ready(), "")
        self.c.session.chmod(0o755); self.assertIn("chmod 700", self.c.ready()); self.c.session.chmod(0o700)
        self.assertIn("number", W.WhatsApp({}).ready())
        self.assertTrue(W.WhatsApp.self_chat_only); self.assertEqual(W.WhatsApp.kind, "linked")
        self.assertEqual(json.loads((HERE / "module.json").read_text())["kind"], "linked")

    @unittest.skipUnless(shutil.which("node"), "node isn't installed")
    def test_js_filter_matches(self):
        r = subprocess.run(["node", "--test", str(HERE / "bridge.test.mjs")], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout[-800:])


if __name__ == "__main__":
    unittest.main()
