"""python3 -I test_ha.py"""
import http.server, json, sys, tempfile, threading, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ha as H


class Fake(http.server.BaseHTTPRequestHandler):
    log = []
    def log_message(self, *a): pass
    def reply(self, obj):
        b = json.dumps(obj).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        Fake.log.append(("GET", self.path, self.headers.get("Authorization")))
        self.reply({"state": "on @rootwarden", "attributes": {"friendly_name": "Desk @person"}})
    def do_POST(self):
        Fake.log.append(("POST", self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))); self.reply([])


class T(unittest.TestCase):
    def setUp(self):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); Fake.log = []
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.sp = Path(tempfile.mkdtemp()) / "tok"; self.sp.write_text("LONG-TOKEN-123")
        self.cfg = {"url": f"http://127.0.0.1:{self.s.server_port}"}
    def tearDown(self): self.s.shutdown(); self.s.server_close()
    def call(self, svc, ent, **cfg): return H.call_service(svc, ent, {**self.cfg, **cfg}, secret_path=self.sp)

    def test_state_reads_with_token_and_strips_mentions(self):
        out = H.state("light.desk", self.cfg, secret_path=self.sp)
        self.assertEqual(Fake.log[0], ("GET", "/api/states/light.desk", "Bearer LONG-TOKEN-123"))
        self.assertNotIn("@", out); self.assertIn("data", out)

    def test_empty_config_is_read_only(self):
        for cfg in ({}, {"allow": []}):
            with self.assertRaises(SystemExit) as e: self.call("light.turn_on", "light.desk", **cfg)
            self.assertIn("read-only", str(e.exception))
        self.assertEqual([x for x in Fake.log if x[0] == "POST"], [])

    def test_allow_list_exact_and_wildcard(self):
        al = {"allow": [{"entity": "light.desk", "services": ["light.turn_on"]}, {"entity": "switch.*", "services": ["switch.toggle"]}]}
        self.call("light.turn_on", "light.desk", **al); self.call("switch.toggle", "switch.fan", **al)
        self.assertEqual([x[1] for x in Fake.log], ["/api/services/light/turn_on", "/api/services/switch/toggle"])
        for svc, ent in (("light.turn_off", "light.desk"), ("light.turn_on", "light.other"), ("switch.turn_on", "switch.fan")):
            with self.assertRaises(SystemExit): self.call(svc, ent, **al)

    def test_dangerous_things_refused_even_if_allowed(self):
        al = {"allow": [{"entity": "lock.*", "services": ["lock.unlock"]}, {"entity": "cover.garage_door", "services": ["cover.open_cover"]},
                        {"entity": "switch.garage_door_opener", "services": ["switch.turn_on"]}, {"entity": "alarm_control_panel.home", "services": ["alarm_control_panel.alarm_disarm"]}]}
        for svc, ent in (("lock.unlock", "lock.front"), ("cover.open_cover", "cover.garage_door"), ("switch.turn_on", "switch.garage_door_opener"), ("alarm_control_panel.alarm_disarm", "alarm_control_panel.home")):
            with self.assertRaises(SystemExit) as e: self.call(svc, ent, **al)
            self.assertIn("dangerous", str(e.exception))
        self.assertEqual(Fake.log, [])

    def test_dangerous_needs_the_exact_listing_no_wildcard(self):
        with self.assertRaises(SystemExit): self.call("lock.unlock", "lock.front", dangerous=[{"entity": "lock.*", "services": ["lock.unlock"]}])
        self.call("lock.lock", "lock.front", dangerous=[{"entity": "lock.front", "services": ["lock.lock"]}])
        self.assertEqual(Fake.log[0][1], "/api/services/lock/lock")
        with self.assertRaises(SystemExit): self.call("lock.unlock", "lock.front", dangerous=[{"entity": "lock.front", "services": ["lock.lock"]}])

    def test_bad_names_and_missing_token_url(self):
        al = {"allow": [{"entity": "light.*", "services": ["light.turn_on"]}]}
        for ent in ("light.desk/../x", "LIGHT.desk", "light"):
            with self.assertRaises(SystemExit): self.call("light.turn_on", ent, **al)
        with self.assertRaises(SystemExit): H.state("light.desk", self.cfg, secret_path=self.sp.parent / "none")
        with self.assertRaises(SystemExit): H.state("light.desk", {"url": "ftp://x"}, secret_path=self.sp)

    def test_token_never_in_errors(self):
        def boom(*a): raise RuntimeError("HTTP 401: bad token LONG-TOKEN-123")
        with self.assertRaises(SystemExit) as e: H.api(self.cfg, "GET", "/x", secret_path=self.sp, call=boom)
        self.assertNotIn("LONG-TOKEN", str(e.exception))


if __name__ == "__main__": unittest.main()
