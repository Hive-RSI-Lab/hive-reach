"""Pure parts, without slixmpp installed (no server is contacted): python3 -I test_xmpp.py"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as X


class Stanza(dict):
    pass


class T(unittest.TestCase):
    def test_sender_is_the_bare_jid(self):
        m = X.to_msg("chat", "Alice@Example.org/phone", "hi", "7")
        self.assertEqual((m.sender, m.chat, m.dm, m.text), ("alice@example.org", "alice@example.org", True, "hi"))

    def test_resource_cannot_change_who_it_is(self):
        self.assertEqual(X.to_msg("chat", "a@x.org/bob@y.org", "hi").sender, "a@x.org")

    def test_groupchat_is_not_dm(self):
        self.assertFalse(X.to_msg("groupchat", "room@conf.x.org/nick", "hi").dm)

    def test_other_types_and_empty_are_dropped(self):
        for t in ("headline", "normal", "error", None): self.assertIsNone(X.to_msg(t, "a@x.org", "hi"))
        self.assertIsNone(X.to_msg("chat", "a@x.org", "")); self.assertIsNone(X.to_msg("chat", "", "hi"))

    def test_handler_skips_own_account_and_passes_others(self):
        c = X.Xmpp({"jid": "bot@x.org/h2"}, "pw"); got = []
        c.on_message(Stanza(type="chat", **{"from": "me@x.org/r"}, body="hello", id="1"), got.append)
        c.on_message(Stanza(type="chat", **{"from": "bot@x.org/other"}, body="echo", id="2"), got.append)
        self.assertEqual([(m.sender, m.text) for m in got], [("me@x.org", "hello")])

    def test_send_without_connection_raises(self):
        with self.assertRaises(RuntimeError): X.Xmpp({"jid": "b@x"}, "p").send("a@x", "hi")

    def test_ready(self):
        self.assertIn("account", X.Xmpp({}, "p").ready()); self.assertIn("password", X.Xmpp({"jid": "b@x"}, "").ready())
        self.assertEqual(X.Xmpp({"jid": "b@x"}, "p").ready(), "")


if __name__ == "__main__": unittest.main()
