"""python3 -I test_hook.py"""
import hashlib, hmac, http.server, json, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook as H


class Fake(http.server.BaseHTTPRequestHandler):
    got = []
    def log_message(self, *a): pass
    def do_POST(self):
        if self.path == "/redir":
            self.send_response(302); self.send_header("Location", "/landed"); self.send_header("Content-Length", "0"); self.end_headers(); return
        Fake.got.append((self.path, self.rfile.read(int(self.headers.get("Content-Length") or 0)), dict(self.headers)))
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()


class T(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}"
        self.d = Path(tempfile.mkdtemp(dir=None)); (self.d / "sec").mkdir()
        self.hp, self.sd = self.d / "hooks.json", self.d / "sec"
        (self.sd / "tok").write_text("hunter2-very-secret-value\n"); (self.sd / "j").write_text('{"a": "another-long-json-secret"}')
    def tearDown(self): self.s.shutdown(); self.s.server_close()
    def add(self, name="x", path="/h", **k): H.add(name, self.url + path, hooks_path=self.hp, **k)

    def test_sends_to_a_listed_hook_only(self):
        self.add(); H.send("x", "hello", self.hp, self.sd)
        self.assertEqual(json.loads(Fake.got[0][1])["text"], "hello")
        with self.assertRaises(SystemExit): H.send("nope", "hello", self.hp, self.sd)

    def test_secret_values_refused(self):
        self.add()
        for t in ("see hunter2-very-secret-value ok", "x another-long-json-secret", "key sk-abcdefghijklmnopqrstuv", "-----BEGIN OPENSSH PRIVATE KEY-----"):
            with self.assertRaises(SystemExit) as e: H.send("x", t, self.hp, self.sd)
            self.assertNotIn("hunter2", str(e.exception))
        self.assertEqual(Fake.got, [])

    def test_redirect_not_followed(self):
        self.add(path="/redir")
        with self.assertRaises(SystemExit) as e: H.send("x", "hi", self.hp, self.sd)
        self.assertIn("not followed", str(e.exception)); self.assertEqual(Fake.got, [])

    def test_signature(self):
        (self.sd / "arm-hook-x").write_text("k3y"); self.add(sign=True); H.send("x", "hi", self.hp, self.sd, now=1000)
        _, body, hd = Fake.got[0]
        want = "sha256=" + hmac.new(b"k3y", b"1000." + body, hashlib.sha256).hexdigest()
        self.assertEqual(hd["X-H2-Signature"], want)

    def test_signing_without_key_refuses(self):
        self.add(sign=True)
        with self.assertRaises(SystemExit): H.send("x", "hi", self.hp, self.sd)

    def test_bad_urls(self):
        for u in ("ftp://a/b", "file:///etc/passwd", "http://u:p@host/x", "nonsense"):
            with self.assertRaises(SystemExit): H.add("x", u, hooks_path=self.hp)

    def test_agent_needs_the_persons_post(self):
        b = self.d / "board.jsonl"; u = self.url + "/h"
        b.write_text(json.dumps({"id": "p1", "from": "person", "text": "add hook " + u}) + "\n" + json.dumps({"id": "p2", "from": "a1234", "text": u}) + "\n")
        for post in (None, "p2", "zz"):
            with self.assertRaises(SystemExit): H.add("x", u, post=post, hooks_path=self.hp, board=b, agent=True)
        H.add("x", u, post="p1", hooks_path=self.hp, board=b, agent=True); self.assertIn("x", H.load(self.hp))
        with self.assertRaises(SystemExit): H.add("y", u + "2", post="p1", hooks_path=self.hp, board=b, agent=True)
        # a URL that is only the start of the person's is another place (…/h → host with a shorter name, or a parent path)
        for part in (u[:-1], u[:-2], u.rsplit(":", 1)[0]):
            with self.assertRaises(SystemExit): H.add("z", part, post="p1", hooks_path=self.hp, board=b, agent=True)

    def test_post_urls_are_exact(self):
        P = H.post_urls
        self.assertEqual(P("use `https://h.example.com/team!` or <https://h.example.com/a?b=1.> or [it](https://h.example.com/c) or https://h.example.com/d ok"),
                         {"https://h.example.com/team!", "https://h.example.com/a?b=1.", "https://h.example.com/c", "https://h.example.com/d"})
        # a bare address that ends in sentence punctuation approves nothing: neither the trimmed nor the untrimmed form
        for t in ("see https://h.example.com/x.", "is it https://h.example.com/x?", "(https://h.example.com/x)", "https://h.example.com/x, then"):
            self.assertEqual(P(t), set(), t)
        self.assertEqual(P("`not a url` <b> https://hooks.example.com/x"), {"https://hooks.example.com/x"})

    def test_trailing_punctuation_is_part_of_the_address(self):
        b = self.d / "board.jsonl"; u = self.url + "/team!"
        b.write_text(json.dumps({"id": "p1", "from": "person", "text": f"hook to `{u}` please. Also {self.url}/q?k=v. Thanks"}) + "\n")
        for other in (u[:-1], self.url + "/q?k=v", self.url + "/q?k=v."):
            with self.assertRaises(SystemExit): H.add("s", other, post="p1", hooks_path=self.hp, board=b, agent=True)
        self.assertNotIn("s", H.load(self.hp))
        H.add("t", u, post="p1", hooks_path=self.hp, board=b, agent=True); self.assertEqual(H.load(self.hp)["t"]["url"], u)

    def test_naming_yourself_person_is_still_an_agent(self):
        import os, subprocess
        r = subprocess.run([sys.executable, "-I", str(Path(H.__file__)), "add", "x", "https://example.com/h"], env={"PATH": os.environ["PATH"], "HOME": str(self.d), "H2_NAME": "person"}, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("only the person", r.stderr)
        self.assertFalse((self.d / ".config/h2/hooks.json").exists())

    def test_unreachable_error_hides_the_address(self):
        H.save({"x": {"url": "http://127.0.0.1:1/tok-abc123"}}, self.hp)
        with self.assertRaises(SystemExit) as e: H.send("x", "hi", self.hp, self.sd)
        self.assertNotIn("abc123", str(e.exception))


if __name__ == "__main__": unittest.main()
