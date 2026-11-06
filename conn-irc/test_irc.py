"""Against a fake IRC server (TLS, loopback, self-signed): python3 -I test_irc.py"""
import base64, os, socket, ssl, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as I

TMP = Path(tempfile.mkdtemp())
CERT, KEY = TMP / "c.pem", TMP / "k.pem"
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", KEY, "-out", CERT, "-days", "2", "-subj", "/CN=localhost",
                "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)


class Server:
    """Speaks just enough IRC. script: lines to push once registered. taken: nicks answered with 433."""
    def __init__(self, script=(), taken=(), tls=True, caps="sasl account-tag account-notify away-notify"):
        self.script, self.taken, self.caps, self.got, self.nick = list(script), set(taken), caps, [], None
        self.sock = socket.socket(); self.sock.bind(("127.0.0.1", 0)); self.sock.listen(1); self.port = self.sock.getsockname()[1]
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); self.ctx.load_cert_chain(CERT, KEY)
        self.done = threading.Event()
        threading.Thread(target=self.run, daemon=True).start()

    def put(self, s, line): s.sendall(line.encode() + b"\r\n")

    def run(self):
        try:
            raw, _ = self.sock.accept()
            s = self.ctx.wrap_socket(raw, server_side=True)
        except OSError:
            self.done.set(); return
        buf = b""
        try:
            while True:
                d = s.recv(4096)
                if not d: break
                buf += d
                while b"\r\n" in buf:
                    l, buf = buf.split(b"\r\n", 1); l = l.decode(); self.got.append(l)
                    if self.reply(s, l): return
        except OSError: pass
        finally: self.done.set()

    def reply(self, s, l):
        w = l.split()
        if l.startswith("CAP LS"): self.put(s, f":srv CAP * LS :{self.caps}")
        elif l.startswith("CAP REQ"): self.put(s, f":srv CAP * ACK :{l.split(':', 1)[1]}")
        elif w[0] == "AUTHENTICATE" and w[1] == "PLAIN": self.put(s, "AUTHENTICATE +")
        elif w[0] == "AUTHENTICATE":
            ok = base64.b64decode(w[1]) == b"\0bot\0pw"
            self.put(s, ":srv 903 * :ok" if ok else ":srv 904 * :bad")
        elif w[0] == "NICK":
            if w[1] in self.taken: self.put(s, f":srv 433 * {w[1]} :in use")
            else: self.nick = w[1]
        elif l == "CAP END":
            self.put(s, f":srv 001 {self.nick} :hi"); self.put(s, "PING :abc")
            for x in self.script: self.put(s, x)
        elif w[0] == "PONG" and self.script is not None: pass
        elif w[0] == "PRIVMSG": pass
        return l.startswith("QUIT")


def make(srv, **kw):
    cfg = {"server": "127.0.0.1", "port": srv.port, "nick": "bot", "cafile": str(CERT)} | kw
    return I.Irc(cfg, "pw")


def run_listen(c, wait=None):
    got = []
    try: c.listen(got.append)
    except Exception as e: got.append(e)
    return got


class T(unittest.TestCase):
    def test_account_is_the_sender_not_the_nick(self):
        srv = Server([
            "@account=alice;msgid=m1 :Mallory!u@h PRIVMSG bot :hello @agent",
            "@account=bob :Eve!u@h PRIVMSG #chan :in a channel",
            ":Anon!u@h PRIVMSG bot :I have no account",
            "@account=* :Anon!u@h PRIVMSG bot :star",
            "ERROR :bye"])
        got = run_listen(make(srv)); srv.done.wait(3)
        msgs = [m for m in got if isinstance(m, C.Msg)]
        self.assertEqual([(m.sender, m.dm, m.text) for m in msgs], [("alice", True, "hello @agent"), ("", False, "")])
        self.assertTrue(any(l == "PONG :abc" for l in srv.got))
        self.assertTrue(isinstance(got[-1], RuntimeError))
        self.assertFalse(any(l.startswith("JOIN") for l in srv.got))

    def test_no_account_gets_no_reply(self):
        srv = Server([":Anon!u@h PRIVMSG bot :hi", "ERROR :bye"])
        run_listen(make(srv)); srv.done.wait(2)
        self.assertFalse(any(l.startswith("PRIVMSG") for l in srv.got))

    def test_nick_in_use_gets_another_and_sasl_user_is_the_configured_one(self):
        srv = Server(["ERROR :bye"], taken={"bot"})
        c = make(srv); run_listen(c); srv.done.wait(3)
        self.assertEqual(c.nick, "bot_"); self.assertIn("NICK bot_", srv.got)

    def test_wrong_password_stops(self):
        srv = Server(); c = I.Irc({"server": "127.0.0.1", "port": srv.port, "nick": "bot", "cafile": str(CERT)}, "nope")
        got = run_listen(c); self.assertIn("SASL", str(got[-1]))

    def test_server_without_account_tag_is_refused(self):
        got = run_listen(make(Server(caps="sasl")))
        self.assertIn("account-tag", str(got[-1]))

    def test_reply_goes_to_the_account_current_nick_in_safe_lines(self):
        srv = Server(["@account=alice :Al!u@h PRIVMSG bot :hi"])
        c = make(srv); box = []
        def inb(m): box.append(m); c.send("alice", "x" * 900 + "\nline\r\nQUIT :evil", ()); c.write("QUIT")
        t = threading.Thread(target=lambda: c.listen(inb), daemon=True); t.start(); srv.done.wait(5)
        lines = [l for l in srv.got if l.startswith("PRIVMSG")]
        self.assertTrue(all(l.startswith("PRIVMSG Al :") and len(l.encode()) <= 420 for l in lines))
        self.assertEqual(len(lines), 5)
        self.assertFalse(any(l.startswith("QUIT :evil") for l in srv.got))

    def test_a_nick_that_changed_or_left_gets_no_reply(self):
        for line in (":ann!u@h QUIT :bye", ":Ann!u@h NICK :other"):
            c = I.Irc({"server": "s", "nick": "n"}, "x"); c.nicks["acct"] = "ann"
            c.on_line(line, None, {}); self.assertEqual(c.nicks, {})

    def test_send_before_anyone_wrote_raises(self):
        with self.assertRaises(RuntimeError): make(Server()).send("alice", "hi")

    def test_plaintext_server_is_not_spoken_to(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); seen = []
        def srv():
            a, _ = s.accept(); a.settimeout(2)
            try: seen.append(a.recv(100))
            except OSError: pass
            a.close()
        threading.Thread(target=srv, daemon=True).start()
        c = I.Irc({"server": "127.0.0.1", "port": s.getsockname()[1], "nick": "bot"}, "pw")
        with self.assertRaises(OSError): c.listen(lambda m: None)
        self.assertFalse(any(b"NICK" in x or b"pw" in x for x in seen))

    def test_ready_needs_tls_and_secret(self):
        self.assertIn("TLS", I.Irc({"server": "s", "nick": "n", "tls": False}, "x").ready())
        self.assertIn("password", I.Irc({"server": "s", "nick": "n"}, "").ready())
        self.assertEqual(I.Irc({"server": "s", "nick": "n"}, "x").ready(), "")

    def test_fit_and_parse(self):
        self.assertTrue(all(len(l.encode()) <= 400 for l in I.fit("é" * 500)))
        self.assertEqual(I.parse("@a=b;c :n!u@h PRIVMSG me :hi there")[:3], ({"a": "b", "c": ""}, "n", "PRIVMSG"))
        self.assertEqual(I.parse("PING :x y")[3], ["x y"])


if __name__ == "__main__": unittest.main()
