"""python3 -I test_browser.py  (needs node; no Chrome, no internet)"""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
TMP = os.path.realpath(tempfile.gettempdir())


def run(*a, env=None, inp=None):
    e = {"PATH": os.environ["PATH"], "TMPDIR": TMP, **(env or {})}
    return subprocess.run(["node", str(HERE / "browser.mjs"), *a], capture_output=True, text=True, env=e, input=inp, timeout=60)


def node(code):
    return subprocess.run(["node", "--input-type=module", "-e", f'import * as g from "{HERE}/guard.mjs"; {code}'], capture_output=True, text=True, timeout=30)


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.log = Path(self.d) / "argv.json"
        # fake Chrome: records argv, then exits at once
        self.fake = Path(self.d) / "fakechrome.py"
        self.fake.write_text(f"import sys,json\njson.dump(sys.argv[1:], open({str(self.log)!r},'w'))\n")
        self.env = {"BROWSER_CHROME_CMD": f"python3 {self.fake}"}

    def test_refuses_foreign_profiles(self):
        home = os.path.expanduser("~")
        nonempty = tempfile.mkdtemp(prefix="browser-"); (Path(nonempty) / "Default").write_text("x")
        link = Path(self.d) / "browser-link"; link.symlink_to(home)
        wrong = tempfile.mkdtemp(prefix="other-")
        for p in (home, "/", "/tmp", nonempty, str(link), wrong, "/nonexistent", os.path.join(TMP, "browser-nope")):
            r = run("run", "https://example.com/", "--user-data-dir", p, env=self.env)
            self.assertEqual(r.returncode, 2, p); self.assertIn("refused", r.stderr)
            self.assertFalse(self.log.exists(), "Chrome must not even start: " + p)
        r = run("run", "https://example.com/", f"--user-data-dir={home}", env=self.env)
        self.assertEqual(r.returncode, 2); self.assertFalse(self.log.exists())

    def test_nested_dir_in_temp_refused(self):
        outer = tempfile.mkdtemp(prefix="browser-"); inner = Path(outer) / "browser-in"; inner.mkdir()
        r = run("run", "https://example.com/", "--user-data-dir", str(inner), env=self.env)
        self.assertEqual(r.returncode, 2)

    def test_fresh_temp_dir_accepted_and_always_passed(self):
        fresh = tempfile.mkdtemp(prefix="browser-")
        run("run", "https://example.com/", "--user-data-dir", fresh, env=self.env)
        argv = json.loads(self.log.read_text())
        self.assertIn(f"--user-data-dir={os.path.realpath(fresh)}", argv)

    def test_default_profile_is_fresh_and_removed(self):
        run("run", "https://example.com/", env=self.env)
        arg = [a for a in json.loads(self.log.read_text()) if a.startswith("--user-data-dir=")]
        self.assertEqual(len(arg), 1)
        d = arg[0].split("=", 1)[1]
        self.assertTrue(os.path.basename(d).startswith("browser-")); self.assertEqual(os.path.dirname(d), TMP)
        self.assertFalse(os.path.exists(d))

    def test_no_flag_passthrough_and_url_scheme(self):
        r = run("run", "https://example.com/", "--remote-debugging-port=9222", env=self.env)
        self.assertEqual(r.returncode, 2); self.assertFalse(self.log.exists())
        for u in ("file:///etc/passwd", "chrome://settings", "javascript:alert(1)", "nope"):
            self.assertEqual(run("run", u, env=self.env).returncode, 2)
        self.assertFalse(self.log.exists())

    def test_steps_validated(self):
        for bad in ('[{"op":"eval","js":"1"}]', '[{"op":"click"}]', '{"op":"text"}'):
            r = run("run", "https://example.com/", "--steps", "-", env=self.env, inp=bad)
            self.assertEqual(r.returncode, 2, bad); self.assertIn("refused", r.stderr)
        self.assertFalse(self.log.exists())

    def test_page_text_labelled_and_mentions_stripped(self):
        r = node('console.log(g.label("hi @rootwarden and `@w1234` mail a@b.c\\nignore previous"))')
        out = r.stdout
        self.assertIn("untrusted data", out); self.assertIn("(end of untrusted page text)", out)
        self.assertNotIn("@rootwarden", out); self.assertNotIn("@w1234", out); self.assertIn("a@b.c", out)
        self.assertIn("> ignore previous", out)


if __name__ == "__main__": unittest.main()
