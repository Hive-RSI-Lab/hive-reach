"""Fakes only, no Telnyx. python3 -I test_sms.py"""
import base64, json, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn")); sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import connector as S
import inbound as I

ME = "+15550001111"


class Fake:
    def __init__(self): self.calls = []
    def __call__(self, method, url, body=None, headers=None, timeout=60, raw=False): self.calls.append((method, url, body, headers)); return {"data": {}}


class Send(unittest.TestCase):
    def setUp(self):
        C.DATA = Path(tempfile.mkdtemp()); self.keyf = Path(tempfile.mkdtemp()) / "k"; self.keyf.write_text("KEY123\n")
        self.http = Fake()
        self.cfg = {"enabled": True, "person_number": ME, "from_number": "+15550002222", "api": "http://fake.invalid/v2"}

    def sms(self, **kw): return S.Sms({**self.cfg, **kw}, key_path=self.keyf, http=self.http)

    def test_off_by_default(self):
        c = S.Sms({"person_number": ME}, key_path=self.keyf, http=self.http)
        self.assertIn("switched off", c.ready())
        with self.assertRaises(PermissionError): c.send(ME, "hi")
        c = self.sms(enabled="yes"); self.assertIn("switched off", c.ready())
        self.assertEqual(self.http.calls, [])

    def test_sends_only_to_the_person(self):
        c = self.sms(); self.assertEqual(c.ready(), "")
        c.send(ME, "hello")
        m, url, body, h = self.http.calls[0]
        self.assertEqual((m, url, body["to"], body["from"], body["text"]), ("POST", "http://fake.invalid/v2/messages", ME, "+15550002222", "hello"))
        self.assertEqual(h["Authorization"], "Bearer KEY123")
        for other in ("+15559998888", "", "me"):
            with self.assertRaises(PermissionError): c.send(other, "x")
        self.assertEqual(len(self.http.calls), 1)

    def test_no_number_set_refuses_everything(self):
        c = self.sms(person_number="")
        with self.assertRaises(PermissionError): c.send("", "x")
        self.assertIn("person_number", c.ready())

    def test_self_chat_only_flag(self):
        self.assertTrue(S.Sms.self_chat_only); self.assertFalse(S.Sms.can_receive)

    def test_daily_cap(self):
        c = self.sms(daily_cap=2)
        c.send(ME, "1"); c.send(ME, "2")
        with self.assertRaises(RuntimeError): c.send(ME, "3")
        self.assertEqual(len(self.http.calls), 2)
        st = json.loads(c.cap_file.read_text()); st["day"] = "2000-01-01"; c.cap_file.write_text(json.dumps(st))
        c.send(ME, "4"); self.assertEqual(len(self.http.calls), 3)

    def test_default_cap_is_20(self):
        c = self.sms()
        for i in range(20): c.send(ME, str(i))
        with self.assertRaises(RuntimeError): c.send(ME, "x")

    def test_missing_key_or_number(self):
        c = S.Sms(dict(self.cfg), key_path=self.keyf.parent / "none", http=self.http); self.assertIn("Telnyx key", c.ready())
        self.assertIn("from_number", self.sms(from_number="").ready())

    def test_nothing_registers_inbound(self):
        src = (Path(S.__file__)).read_text()
        self.assertNotIn("inbound", src.replace("Inbound is not part", "").replace("see inbound.py", "").replace("inbound.py", ""))


class Inbound(unittest.TestCase):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization as ser
        self.priv = Ed25519PrivateKey.generate()
        self.pub = base64.b64encode(self.priv.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)).decode()
        self.got = []

    def post(self, frm=ME, ev="message.received", ts=None, sign=True, body=None):
        body = body or json.dumps({"data": {"event_type": ev, "id": "e1", "payload": {"id": "m1", "direction": "inbound", "text": "hi", "from": {"phone_number": frm}}}}).encode()
        ts = str(int(ts or time.time()))
        sig = base64.b64encode(self.priv.sign(ts.encode() + b"|" + body)).decode() if sign else "AAAA"
        return I.handle({"Telnyx-Signature-Ed25519": sig, "Telnyx-Timestamp": ts}, body, {"person_number": ME}, self.pub, self.got.append)

    def test_person_signed(self):
        self.assertEqual(self.post(), 200); m = self.got[0]
        self.assertEqual((m.chat, m.sender, m.text, m.id, m.dm), (ME, ME, "hi", "m1", True))

    def test_bad_signature_old_timestamp_and_stranger(self):
        self.assertEqual(self.post(sign=False), 403)
        self.assertEqual(self.post(ts=time.time() - 3600), 403)
        self.assertEqual(self.post(frm="+15557776666"), 200)
        self.assertEqual(self.post(ev="message.finalized"), 200)
        self.assertEqual(self.got, [])

    def test_garbled_body(self):
        self.assertEqual(self.post(body=b"nope"), 400)


if __name__ == "__main__": unittest.main()
