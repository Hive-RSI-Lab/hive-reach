"""python3 -I test_browser.py  (needs node; no Chrome, no internet)"""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
TMP = os.path.realpath(tempfile.gettempdir())
# browser.mjs drives Chrome through the dashboard's chrome_pipe.mjs; the cases that launch the fake Chrome need it.
PIPE = os.environ.get("BROWSER_PIPE") or os.path.join(os.path.expanduser("~"), "modules/dash/web/test/chrome_pipe.mjs")
needs_pipe = unittest.skipUnless(os.path.exists(PIPE), "needs the dash module's chrome_pipe.mjs (set BROWSER_PIPE)")


def run(*a, env=None, inp=None):
    e = {"PATH": os.environ["PATH"], "TMPDIR": TMP, "BROWSER_PIPE": PIPE, **(env or {})}
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

    @needs_pipe
    def test_fresh_temp_dir_accepted_and_always_passed(self):
        fresh = tempfile.mkdtemp(prefix="browser-")
        run("run", "https://example.com/", "--user-data-dir", fresh, env=self.env)
        argv = json.loads(self.log.read_text())
        self.assertIn(f"--user-data-dir={os.path.realpath(fresh)}", argv)

    @needs_pipe
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

    def test_local_addresses_refused(self):
        bad = ["http://127.0.0.1/", "http://localhost:8123/", "http://printer.local/", "http://router.lan/", "http://nas/", "http://10.0.0.1/", "http://192.168.1.1/",
               "http://172.20.0.1/", "http://169.254.169.254/", "http://100.64.0.1/", "http://0.0.0.0/", "http://2130706433/", "http://0x7f.1/", "http://[::1]/",
               "http://[::ffff:127.0.0.1]/", "http://[::ffff:a00:1]/", "http://[fe80::1]/", "http://[fd00::1]/", "http://[64:ff9b::7f00:1]/", "http://[2002:c0a8:101::]/",
               "http://[::127.0.0.1]/", "http://LOCALHOST./", "http://a.home.arpa/"]
        good = ["https://example.com/", "http://93.184.216.34/", "http://[2606:2800:220:1::1]/", "http://[64:ff9b::5db8:d822]/"]
        code = f"for (const u of {json.dumps(bad)}) {{ try {{ g.checkUrl(u); console.log('LET ' + u); }} catch {{}} }}" \
               f"for (const u of {json.dumps(good)}) {{ try {{ g.checkUrl(u); }} catch (e) {{ console.log('REFUSED ' + u); }} }}" \
               "const fake = async () => [{address: '93.184.216.34'}, {address: '10.0.0.5'}];" \
               "await g.checkHost('https://sneaky.example/', fake).then(() => console.log('LET sneaky'), () => {});" \
               "await g.checkHost('https://ok.example/', async () => [{address: '93.184.216.34'}]);" \
               "await g.checkHost('https://nodns.example/', async () => { throw Error('ENOTFOUND'); });"
        r = node(code); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(run("run", "http://127.0.0.1:8123/", env=self.env).returncode, 2); self.assertFalse(self.log.exists())

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
