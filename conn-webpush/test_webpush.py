"""python3 -I test_webpush.py: the RFC 8291 example, plus delivery to a fake push service on loopback. No internet, nothing switched on."""
import base64, http.server, json, os, stat, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "conn")); sys.path.insert(0, str(HERE))
import connector as N
import conn as C
import webpush_subs as S
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

UNB = S.unb64

# RFC 8291 appendix A
V_PLAIN = "V2hlbiBJIGdyb3cgdXAsIEkgd2FudCB0byBiZSBhIHdhdGVybWVsb24"
V_AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
V_AS_PUBLIC = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8"
V_UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
V_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
V_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
V_OUT = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


class Fake(http.server.BaseHTTPRequestHandler):
    got = []; answers = {}
    def log_message(self, *a): pass
    def do_POST(self):
        Fake.got.append((self.path, self.rfile.read(int(self.headers.get("Content-Length") or 0)), dict(self.headers)))
        code = Fake.answers.get(self.path, 201)
        self.send_response(code)
        if code in (301, 302, 307): self.send_header("Location", "/moved")
        self.send_header("Content-Length", "0"); self.end_headers()


def browser():
    """A pretend browser: its keypair and auth secret, and how it would decrypt."""
    key = ec.generate_private_key(ec.SECP256R1()); auth = os.urandom(16)
    return key, auth, N.b64(N.public_bytes(key)), N.b64(auth)


def open_body(body, key, auth):
    salt, rs, n = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_public = body[21:21 + n]
    shared = key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = N.hkdf(auth, shared, b"WebPush: info\x00" + N.public_bytes(key) + as_public, 32)
    cek = N.hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16); nonce = N.hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    return rs, AESGCM(cek).decrypt(nonce, body[21 + n:], None)


class Rfc(unittest.TestCase):
    def test_rfc_8291_appendix_a(self):
        out = N.encrypt(UNB(V_PLAIN), UNB(V_UA_PUBLIC), UNB(V_AUTH), N.key_from_scalar(UNB(V_AS_PRIVATE)), UNB(V_SALT))
        self.assertEqual(N.b64(out), V_OUT)

    def test_the_rfc_keys_agree(self):
        self.assertEqual(N.b64(N.public_bytes(N.key_from_scalar(UNB(V_AS_PRIVATE)))), V_AS_PUBLIC)


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.home = Path(self.t.name)
        self.old = C.SECRETS, C.CONFIG, C.DATA
        C.SECRETS = self.home / "secrets"; C.CONFIG = self.home / "conn"; C.DATA = self.home / "data"
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.got = []; Fake.answers = {}
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.origin = f"http://127.0.0.1:{self.s.server_port}"
    def tearDown(self):
        self.s.shutdown(); self.s.server_close(); C.SECRETS, C.CONFIG, C.DATA = self.old; self.t.cleanup()
    def conn(self, **cfg):
        changes = N.WebPush({}, "").setup()
        return N.WebPush({**changes, "allow_origins": [self.origin], **cfg}, C.read_secret("webpush"))
    def sub(self, path="/ep", **more):
        key, auth, p, a = browser()
        c = S.clean({"endpoint": self.origin + path, "keys": {"p256dh": p, "auth": a}}, allow=(self.origin,))
        S.Store(C.DATA / "webpush").add({**c, **more})
        return key, auth


class Setup(Base):
    def test_key_is_private_and_stays(self):
        one = N.WebPush({}, "").setup()
        f = C.secret_path("webpush")
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(f.parent.stat().st_mode), 0o700)
        words = f.read_text()
        two = N.WebPush({}, C.read_secret("webpush")).setup()
        self.assertEqual(f.read_text(), words); self.assertEqual(one["public_key"], two["public_key"])

    def test_setup_says_nothing_and_config_has_no_private_part(self):
        out = subprocess.run([sys.executable, "-I", "-c", f"""
import sys; sys.path.insert(0, {str(HERE)!r})
import connector as N
from pathlib import Path
N.C.SECRETS = Path({str(self.home / 'quiet')!r})
print(N.WebPush({{}}, '').setup())"""], capture_output=True, text=True, check=True)
        secret = (self.home / "quiet/conn-webpush").read_text()
        self.assertNotIn(secret, out.stdout + out.stderr)
        self.assertIn("public_key", out.stdout)

    def test_ready_says_what_is_missing(self):
        self.assertIn("conn on webpush", N.WebPush({}, "").ready())
        self.assertIn("public key", N.WebPush({}, N.b64(b"k" * 32)).ready())
        self.assertEqual(self.conn().ready(), "")

    def test_ready_and_import_need_no_package(self):
        # The unit's ExecStartPre runs this on the system Python, outside uv.
        out = subprocess.run([sys.executable, "-I", "-c", f"""
import sys; sys.path.insert(0, {str(HERE)!r})
import connector as N
N.WebPush({{}}, '').ready()
print('cryptography' in sys.modules)"""], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "False")

    def test_one_way_and_the_config_needed_to_be_routed(self):
        ch = N.WebPush({}, "").setup()
        self.assertFalse(N.WebPush.can_receive)
        self.assertEqual((ch["pings"], ch["home"]), ("short", "browser"))


class Send(Base):
    def test_contentless_encrypted_and_signed(self):
        key, auth = self.sub(link="https://h2.example/")
        c = self.conn(); c.send("browser", "the secret plan")
        path, body, hd = Fake.got[0]
        self.assertNotIn(b"secret", body)
        hd = {k.lower(): v for k, v in hd.items()}
        self.assertEqual(hd["content-encoding"], "aes128gcm")
        rs, plain = open_body(body, key, auth)
        self.assertEqual(rs, 4096)
        self.assertEqual(plain[-1], 2)
        self.assertEqual(json.loads(plain[:-1]), {"title": "H2", "body": N.LINE, "url": "https://h2.example/"})
        for word in ("secret", "plan"): self.assertNotIn(word, json.dumps(hd))

    def test_vapid_token_verifies_against_the_public_key(self):
        self.sub(); c = self.conn(); c.send("browser", "x")
        hd = {k.lower(): v for k, v in Fake.got[0][2].items()}
        scheme, rest = hd["authorization"].split(" ", 1)
        parts = dict(p.strip().split("=", 1) for p in rest.split(","))
        self.assertEqual(scheme, "vapid"); self.assertEqual(parts["k"], c.cfg["public_key"])
        head, claims, sig = parts["t"].split(".")
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), UNB(parts["k"]))
        raw = UNB(sig); self.assertEqual(len(raw), 64)
        der = utils.encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        pub.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(InvalidSignature): pub.verify(der, b"other", ec.ECDSA(hashes.SHA256()))
        got = json.loads(UNB(claims))
        self.assertEqual(json.loads(UNB(head))["alg"], "ES256")
        self.assertEqual(got["aud"], self.origin)
        self.assertLessEqual(got["exp"], time.time() + 86400)
        self.assertTrue(got["sub"].startswith(("https://", "mailto:")))

    def test_gone_removes_only_that_one(self):
        for code in (404, 410):
            Fake.answers = {"/dead": code}
            self.sub("/dead"); self.sub("/live")
            self.conn().send("browser", "x")
            left = [s["endpoint"] for s in S.Store(C.DATA / "webpush").load()]
            self.assertEqual(left, [self.origin + "/live"])

    def test_nobody_got_it_raises_so_the_bridge_retries_without_saying_where(self):
        Fake.answers = {"/busy": 503}; self.sub("/busy")
        with self.assertRaises(RuntimeError) as e: self.conn().send("browser", "x")
        self.assertNotIn(self.origin, str(e.exception))
        self.assertEqual(len(S.Store(C.DATA / "webpush").load()), 1)

    def test_one_got_it_does_not_repeat_for_everyone(self):
        Fake.answers = {"/busy": 503}; self.sub("/busy"); self.sub("/live")
        self.conn().send("browser", "x")

    def test_no_subscribers_is_not_a_failure(self):
        self.conn().send("browser", "x"); self.assertEqual(Fake.got, [])

    def test_a_redirect_is_not_followed(self):
        Fake.answers = {"/away": 307}; self.sub("/away")
        with self.assertRaises(RuntimeError): self.conn().send("browser", "x")
        self.assertEqual([g[0] for g in Fake.got], ["/away"])

    def test_an_address_put_in_the_file_by_hand_is_never_posted_to(self):
        key, auth, p, a = browser()
        S.Store(C.DATA / "webpush").add({"endpoint": self.origin + "/evil", "p256dh": p, "auth": a})
        N.WebPush({**N.WebPush({}, "").setup()}, C.read_secret("webpush")).send("browser", "x")
        self.assertEqual(Fake.got, [])
        self.assertEqual(S.Store(C.DATA / "webpush").load(), [])

    def test_bad_browser_keys_drop_the_subscription(self):
        p = N.b64(b"\x04" + b"\xff" * 64)
        S.Store(C.DATA / "webpush").add({"endpoint": self.origin + "/bad", "p256dh": p, "auth": N.b64(b"a" * 16)})
        self.conn().send("browser", "x")
        self.assertEqual(S.Store(C.DATA / "webpush").load(), [])

    def test_a_http_click_address_is_not_used(self):
        key, auth = self.sub(link="http://plain.example/")
        self.conn(click="https://c.example/").send("browser", "x")
        self.assertEqual(json.loads(open_body(Fake.got[0][1], key, auth)[1][:-1])["url"], "https://c.example/")


class Addresses(unittest.TestCase):
    def test_only_push_services(self):
        for good in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/x", "https://web.push.apple.com/Qx",
                     "https://wns2-par02p.notify.windows.com/w/?token=a", "https://FCM.googleapis.com:443/x"):
            self.assertTrue(S.endpoint_ok(good), good)
        for bad in ("http://fcm.googleapis.com/x", "https://127.0.0.1/x", "https://localhost/x", "https://169.254.169.254/latest", "https://fcm.googleapis.com.evil.example/x",
                    "https://evilpush.apple.com/x", "https://fcm.googleapis.com@evil.example/x", "https://evil.example\\@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x",
                    "https://fcm.googleapis.com:bad/x", "file:///etc/passwd", "https://fcm.googleapis.com/a b", "https://fcm.googleapis.com/" + "x" * 3000, "", None, 7):
            self.assertFalse(S.endpoint_ok(bad), bad)

    def test_keys_are_checked(self):
        ok = {"p256dh": N.b64(b"\x04" + b"k" * 64), "auth": N.b64(b"a" * 16)}
        e = "https://fcm.googleapis.com/x"
        self.assertEqual(S.clean({"endpoint": e, "keys": ok})["p256dh"], ok["p256dh"])
        for bad in ({**ok, "auth": "x"}, {**ok, "p256dh": N.b64(b"\x03" + b"k" * 64)}, {**ok, "auth": 5}, {**ok, "auth": "!!!!"}):
            with self.assertRaises(ValueError): S.clean({"endpoint": e, "keys": bad})
        for bad in (None, [], {"endpoint": e}, {"endpoint": e, "keys": "x"}):
            with self.assertRaises(ValueError): S.clean(bad)

    def test_the_file_is_private_and_capped(self):
        with tempfile.TemporaryDirectory() as t:
            st = S.Store(Path(t) / "w")
            for i in range(S.MAX_SUBS + 5): st.add({"endpoint": f"https://fcm.googleapis.com/{i}"})
            subs = st.load()
            self.assertEqual(len(subs), S.MAX_SUBS); self.assertTrue(subs[-1]["endpoint"].endswith(str(S.MAX_SUBS + 4)))
            self.assertEqual(stat.S_IMODE(st.file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(st.dir.stat().st_mode), 0o700)

    def test_concurrent_writers_keep_every_change(self):
        with tempfile.TemporaryDirectory() as t:
            code = f"import sys; sys.path.insert(0, {str(HERE)!r}); import webpush_subs as S; st = S.Store({t!r}); [st.add({{'endpoint': sys.argv[1] + str(i)}}) for i in range(5)]"
            ps = [subprocess.Popen([sys.executable, "-I", "-c", code, w]) for w in "ab"]
            for p in ps: self.assertEqual(p.wait(), 0)
            self.assertEqual(len(S.Store(t).load()), 10)

    def test_act_needs_the_key_and_a_known_word(self):
        with tempfile.TemporaryDirectory() as t:
            sub = {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": N.b64(b"\x04" + b"k" * 64), "auth": N.b64(b"a" * 16)}}
            self.assertFalse(S.view(t)["available"])
            with self.assertRaises(ValueError): S.act(t, {"do": "subscribe", "subscription": sub})
            S.config_file(t).parent.mkdir(parents=True)
            S.config_file(t).write_text(json.dumps({"public_key": sub["keys"]["p256dh"]}))
            self.assertEqual(S.act(t, {"do": "subscribe", "subscription": sub}, "https://a.example/")["count"], 1)
            self.assertEqual(S.Store(S.state_dir(t)).load()[0]["link"], "https://a.example/")
            self.assertEqual(S.act(t, {"do": "unsubscribe", "endpoint": sub["endpoint"]})["count"], 0)
            for d in ({"do": "x"}, {"do": "unsubscribe"}):
                with self.assertRaises(ValueError): S.act(t, d)


class ThroughTheBridge(Base):
    def test_a_post_for_the_person_becomes_one_push(self):
        board = self.home / "board.jsonl"; board.write_text("")
        self.sub(); c = self.conn()
        b = C.Bridge("webpush", c.send, cfg=c.cfg, board=board, state=self.home / "state.db", log=lambda s: None)
        with board.open("a") as f: f.write(json.dumps({"id": "1", "from": "a1b2c", "to": ["@person"], "thread": "job", "text": "the secret plan"}) + "\n")
        b.pump()
        self.assertEqual(len(Fake.got), 1); self.assertNotIn(b"secret", Fake.got[0][1])


if __name__ == "__main__": unittest.main()
