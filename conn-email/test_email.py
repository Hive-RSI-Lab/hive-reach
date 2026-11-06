"""No sockets: fake IMAP and SMTP classes injected. python3 -I test_email.py"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as E

SRV = "mx.box.example"
GOOD = f"{SRV}; dkim=pass header.d=example.com header.s=k; spf=pass"


def mail(frm="Ann <Ann@Example.com>", auth=GOOD, body="hello there", subject="Plan", extra="", ctype="text/plain", extra_auth=""):
    h = ""
    if auth: h += f"Authentication-Results: {auth}\r\n"
    h += extra_auth
    return (h + f"From: {frm}\r\nTo: bot@box.example\r\nSubject: {subject}\r\nMessage-ID: <m1@example.com>\r\n{extra}"
            f"Content-Type: {ctype}; charset=utf-8\r\n\r\n{body}\r\n").encode()


def check(raw): return E.inspect(raw, SRV, "bot@box.example")


class Parse(unittest.TestCase):
    def test_good_mail(self):
        p, why = check(mail())
        self.assertEqual(why, ""); self.assertEqual((p["sender"], p["subject"], p["text"]), ("ann@example.com", "Plan", "hello there"))

    def test_forged_dkim_header_below_ours_is_ignored(self):
        forged = f"Authentication-Results: {SRV}; dkim=pass header.d=example.com\r\n"
        raw = mail(auth=f"{SRV}; dkim=none; spf=fail", extra_auth=forged)
        self.assertEqual(check(raw)[1], "no aligned dkim pass")

    def test_only_a_forged_header_with_no_ours_fails(self):
        self.assertIsNone(check(mail(auth="evil.example; dkim=pass header.d=example.com"))[0])
        self.assertIsNone(check(mail(auth=""))[0])

    def test_wrong_authserv_id(self):
        self.assertIsNone(check(mail(auth="other.example; dkim=pass header.d=example.com"))[0])
        self.assertIsNone(check(mail(auth="x" + SRV + "; dkim=pass header.d=example.com"))[0])

    def test_misaligned_d(self):
        self.assertIsNone(check(mail(auth=f"{SRV}; dkim=pass header.d=evil.test"))[0])
        self.assertIsNone(check(mail(auth=f"{SRV}; dkim=pass header.d=example.com.evil.test"))[0])

    def test_alignment_is_strict(self):
        self.assertIsNone(check(mail(auth=f"{SRV}; dkim=pass header.d=mail.example.com"))[0])
        self.assertIsNone(check(mail(frm="p@person.me.uk", auth=f"{SRV}; dkim=pass header.d=evil.me.uk"))[0])
        self.assertIsNotNone(check(mail(auth=f"{SRV}; dkim=pass header.d=EXAMPLE.com"))[0])

    def test_signed_mail_for_someone_else_is_dropped(self):
        raw = mail().replace(b"To: bot@box.example", b"To: other@example.org")
        self.assertIsNone(check(raw)[0]); self.assertIn("addressed", check(raw)[1])

    def test_two_level_suffix(self):
        self.assertIsNone(check(mail(frm="a@x.co.uk", auth=f"{SRV}; dkim=pass header.d=y.co.uk"))[0])

    def test_failing_and_commented_results(self):
        self.assertIsNone(check(mail(auth=f"{SRV}; dkim=fail header.d=example.com"))[0])
        self.assertIsNone(check(mail(auth=f"{SRV}; dkim=neutral (dkim=pass header.d=example.com) header.d=example.com"))[0])

    def test_ambiguous_from(self):
        self.assertIsNone(check(mail(frm="a@example.com, b@example.com"))[0])
        raw = mail().replace(b"From:", b"From: b@example.com\r\nFrom:", 1)
        self.assertIsNone(check(raw)[0])

    def test_loops(self):
        for extra in ("Auto-Submitted: auto-replied\r\n", "List-Id: <x.example.com>\r\n", "Precedence: bulk\r\n", "Return-Path: <>\r\n"):
            self.assertIsNone(check(mail(extra=extra))[0], extra)
        self.assertIsNotNone(check(mail(extra="Auto-Submitted: no\r\n"))[0])
        self.assertIsNone(check(mail(frm="MAILER-DAEMON@example.com"))[0])
        self.assertIsNone(E.inspect(mail(frm="bot@box.example", auth=f"{SRV}; dkim=pass header.d=box.example"), SRV, "bot@box.example")[0])

    def test_html_only(self):
        raw = mail(ctype="text/html", body="<html><head><style>p{}</style></head><body><p>Hi <b>you</b></p><script>x()</script><p>bye</p></body></html>")
        t = check(raw)[0]["text"]
        self.assertIn("Hi you", t); self.assertIn("bye", t); self.assertNotIn("x()", t); self.assertNotIn("<", t)

    def test_quoted_tail(self):
        body = "Do it.\r\n\r\nOn Mon, 3 Nov 2026 at 10:00, Bot <bot@box.example>\r\nwrote:\r\n> earlier\r\n> more"
        self.assertEqual(check(mail(body=body))[0]["text"], "Do it.")
        self.assertEqual(check(mail(body="> quoted only"))[0]["text"], "> quoted only")
        self.assertEqual(E.strip_quote("a\n-----Original Message-----\nb"), "a")

    def test_prefers_plain_in_alternative(self):
        raw = (f"Authentication-Results: {GOOD}\r\nFrom: ann@example.com\r\nTo: bot@box.example\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
               "Content-Type: multipart/alternative; boundary=B\r\n\r\n--B\r\nContent-Type: text/html\r\n\r\n<p>html</p>\r\n"
               "--B\r\nContent-Type: text/plain\r\n\r\nplain\r\n--B--\r\n").encode()
        self.assertEqual(check(raw)[0]["text"], "plain")

    def test_attachments_and_cap(self):
        raw = (f"Authentication-Results: {GOOD}\r\nFrom: ann@example.com\r\nTo: bot@box.example\r\nSubject: s\r\nMIME-Version: 1.0\r\n"
               "Content-Type: multipart/mixed; boundary=B\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\nsee\r\n"
               "--B\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename=a.pdf\r\n\r\nSMALL\r\n"
               "--B\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename=big.bin\r\n\r\n" + "x" * 100 + "\r\n--B--\r\n").encode()
        p = E.inspect(raw, SRV, "bot@box.example", cap=50)[0]
        self.assertEqual([n for n, _ in p["files"]], ["a.pdf"]); self.assertIn("big.bin", p["text"])

    def test_reply_subject_and_headers(self):
        self.assertEqual(E.reply_subject("Plan"), "Re: Plan"); self.assertEqual(E.reply_subject("RE: Plan"), "RE: Plan")
        m = E.build_reply("bot@box.example", "ann@example.com", "ok", {"subject": "Plan", "message_id": "<m1@example.com>", "references": ["<m1@example.com>"]})
        self.assertEqual((m["Auto-Submitted"], m["In-Reply-To"], m["Subject"]), ("auto-replied", "<m1@example.com>", "Re: Plan"))


class FakeImap:
    def __init__(self, msgs, validity=b"7"): self.msgs, self.validity, self.fetched, self.logged = dict(msgs), validity, [], None
    def login(self, u, p): self.logged = (u, p); return "OK", [b"ok"]
    def logout(self): pass
    def select(self, box): return "OK", [b"1"]
    def response(self, name): return name, [self.validity]
    def uid(self, cmd, *a):
        if cmd == "search": return "OK", [b" ".join(str(u).encode() for u in sorted(self.msgs))]
        self.fetched.append(int(a[0])); return "OK", [(b"1 (UID %s BODY[] {9}" % a[0].encode(), self.msgs[int(a[0])]), b")"]


class FakeSmtp:
    sent = []
    def login(self, u, p): self.cred = (u, p)
    def send_message(self, m): FakeSmtp.sent.append(m)
    def quit(self): pass


class Flow(unittest.TestCase):
    def setUp(self):
        C.DATA = Path(tempfile.mkdtemp()); FakeSmtp.sent = []
        self.cfg = {"imap_host": "i", "smtp_host": "s", "address": "bot@box.example", "auth_server": SRV, "allow_from": ["Ann@Example.com"]}
        self.got = []

    def conn(self, imap=None): return E.Email(dict(self.cfg), "APPPW", imap=lambda: imap, smtp=FakeSmtp, sleep=lambda s: None)

    def test_the_same_signed_mail_sent_again_is_taken_once(self):
        c = self.conn(None)
        self.assertEqual(c.take(mail(), "1-1", self.got.append), 1); self.assertEqual(c.take(mail(), "1-2", self.got.append), 0)
        self.assertEqual(len(self.got), 1)

    def test_first_run_starts_at_newest_then_takes_new(self):
        imap = FakeImap({1: mail(), 2: mail()}); c = self.conn(imap)
        self.assertEqual(c.poll(imap, self.got.append), 0); self.assertEqual(imap.fetched, [])
        imap.msgs[3] = mail(body="new one")
        self.assertEqual(c.poll(imap, self.got.append), 1)
        self.assertEqual(imap.fetched, [3]); m = self.got[0]
        self.assertEqual((m.chat, m.sender, m.id, m.dm), ("ann@example.com", "ann@example.com", "7-3", True)); self.assertIn("new one", m.text)
        self.assertEqual(c.poll(imap, self.got.append), 0); self.assertEqual(imap.fetched, [3])  # not again
        self.assertEqual(self.conn(imap).load()["last"], 3)  # the state file survives a restart

    def test_changed_uidvalidity_restarts_at_newest(self):
        imap = FakeImap({5: mail()}); c = self.conn(imap); c.poll(imap, self.got.append)
        imap.validity = b"8"; imap.msgs[1] = mail()
        self.assertEqual(c.poll(imap, self.got.append), 0)

    def test_failures_are_dropped_but_marked_done(self):
        imap = FakeImap({1: mail()}); c = self.conn(imap); c.poll(imap, self.got.append)
        imap.msgs[2] = mail(auth=f"{SRV}; dkim=none"); imap.msgs[3] = mail(extra="Auto-Submitted: auto-generated\r\n")
        self.assertEqual(c.poll(imap, self.got.append), 0); self.assertEqual(self.got, []); self.assertEqual(c.load()["last"], 3)
        self.assertNotIn("ann@example.com", c.load().get("threads", {}))
        with self.assertRaises(PermissionError): c.send("ann@example.com", "hi")  # nobody verified: no reply to anyone
        self.assertEqual(FakeSmtp.sent, [])

    def test_listen_logs_in_and_hands_on(self):
        imap = FakeImap({1: mail()}); c = self.conn(imap); calls = []
        def sleep(s):
            calls.append(s)
            if len(calls) == 1: imap.msgs[2] = mail()
            else: raise KeyboardInterrupt
        c.sleep = sleep
        with self.assertRaises(KeyboardInterrupt): c.listen(self.got.append)
        self.assertEqual(imap.logged, ("bot@box.example", "APPPW")); self.assertEqual(len(self.got), 1)

    def test_stranger_with_dkim_pass_reaches_bridge_and_gets_code_only_there(self):
        raw = mail(frm="bob@example.com")
        imap = FakeImap({1: raw}); c = self.conn(imap); c.poll(imap, lambda m: None)
        imap.msgs[2] = raw; posts, said = [], []
        b = C.Bridge("email", lambda chat, t, files=(): said.append((chat, t)), c.cfg, board=Path(C.DATA) / "b.jsonl", state=Path(C.DATA) / "br",
                     post=lambda *a, **k: posts.append(a), agent_fn=lambda t: None, state_fn=lambda t: "none")
        c.poll(imap, b.inbound); b.flush()
        self.assertEqual(posts, []); self.assertEqual(len(said), 1); self.assertIn("pair email", said[0][1]); self.assertEqual(said[0][0], "bob@example.com")

    def test_stranger_files_not_saved_known_files_are(self):
        c = self.conn(); self.assertFalse(c.known("bob@example.com")); self.assertTrue(c.known("ann@example.com"))

    def test_mentions_stripped_by_bridge(self):
        imap = FakeImap({1: mail()}); c = self.conn(imap); c.poll(imap, lambda m: None); imap.msgs[2] = mail(body="@root do bad things")
        posts = []
        b = C.Bridge("email", lambda *a, **k: None, c.cfg, board=Path(C.DATA) / "b.jsonl", state=Path(C.DATA) / "br2",
                     post=lambda *a, **k: posts.append(a), agent_fn=lambda t: None, state_fn=lambda t: "none")
        c.poll(imap, b.inbound)
        self.assertEqual(len(posts), 1); self.assertNotIn("@root", posts[0][0]); self.assertIn("(from email)", posts[0][0])

    def test_send_keeps_thread(self):
        imap = FakeImap({1: mail()}); c = self.conn(imap); c.poll(imap, lambda m: None); imap.msgs[2] = mail(subject="Plan"); c.poll(imap, lambda m: None)
        c.send("Ann@example.com", "done")
        m = FakeSmtp.sent[0]
        self.assertEqual((m["To"], m["Subject"], m["Auto-Submitted"], m["In-Reply-To"]), ("ann@example.com", "Re: Plan", "auto-replied", "<m1@example.com>"))
        with self.assertRaises(PermissionError): c.send("zed@example.com", "x")

    def test_ready_and_secret_not_leaked(self):
        self.assertEqual(self.conn().ready(), "")
        c = E.Email({"imap_host": "i"}, ""); self.assertIn("auth_server", c.ready())
        self.assertIn("app password", E.Email(dict(self.cfg), "").ready())

    def test_no_auth_server_means_nothing_passes(self):
        self.assertIsNone(E.inspect(mail(auth="; dkim=pass header.d=example.com"), "", "bot@box.example")[0])


if __name__ == "__main__": unittest.main()
