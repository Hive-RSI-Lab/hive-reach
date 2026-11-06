"""python3 -I test_remind.py"""
import datetime as dt, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import remind as R

NOW = dt.datetime(2026, 11, 5, 10, 0)


class T(unittest.TestCase):
    def setUp(self): self.st = Path(tempfile.mkdtemp()) / "r.json"
    def add(self, *a, **k): return R.add(*a, store=self.st, now=NOW, thread=k.pop("thread", "t1"), **k)

    def test_when_forms(self):
        self.assertEqual(R.parse_when("+90m", NOW), NOW + dt.timedelta(minutes=90))
        self.assertEqual(R.parse_when("09:00", NOW), dt.datetime(2026, 11, 6, 9, 0))
        self.assertEqual(R.parse_when("2026-11-06 09:30", NOW), dt.datetime(2026, 11, 6, 9, 30))
        with self.assertRaises(SystemExit): R.parse_when("someday", NOW)

    def test_cron_next(self):
        self.assertEqual(R.next_after("30 9 * * *", NOW), dt.datetime(2026, 11, 6, 9, 30))
        self.assertEqual(R.next_after("*/20 * * * *", NOW), dt.datetime(2026, 11, 5, 10, 20))
        self.assertEqual(R.next_after("0 8 * * 1", NOW), dt.datetime(2026, 11, 9, 8, 0))   # Monday
        self.assertEqual(R.next_after("0 8 * * 1-5", NOW), dt.datetime(2026, 11, 6, 8, 0))
        self.assertEqual(R.next_after("0 8 29 2 *", NOW), dt.datetime(2028, 2, 29, 8, 0))
        for bad in ("* * *", "61 * * * *", "a b c d e", "*/0 * * * *"):
            with self.assertRaises(SystemExit): R.next_after(bad, NOW)

    def test_too_often_refused(self):
        with self.assertRaises(SystemExit): self.add("every", "* * * * *", "x")
        with self.assertRaises(SystemExit): self.add("every", "*/5 * * * *", "x")
        self.add("every", "*/15 * * * *", "ok")

    def test_names(self):
        self.add("at", "+1h", "@a1b2c look", to="a1b2c"); self.add("at", "+1h", "hi")
        for to, text in (("rootwarden", "x"), ("warden", "x"), ("person", "go @rootwarden"), ("person", "see @w1a2b"), ("person", "@warden do it"), ("new", "x"), ("person", "@new go"), ("claude", "x")):
            with self.assertRaises(SystemExit, msg=(to, text)): self.add("at", "+1h", text, to=to)

    def test_tick_posts_once_and_reschedules(self):
        got = []; self.add("at", "+10m", "one", to="a1b2c"); self.add("every", "0 12 * * *", "daily"); self.add("at", "+2h", "later")
        fired = R.tick(self.st, NOW + dt.timedelta(hours=3), lambda it, late: got.append((it["to"], it["text"], late)))
        self.assertEqual(len(fired), 3)
        left = R.load(self.st); self.assertEqual([i["cron"] for i in left], ["0 12 * * *"]); self.assertEqual(left[0]["due"], "2026-11-06T12:00")
        self.assertEqual(R.tick(self.st, NOW + dt.timedelta(hours=3), lambda *a: got.append(1)), [])

    def test_failed_post_is_kept(self):
        self.add("at", "+1m", "x")
        def boom(it, late): raise OSError
        self.assertEqual(R.tick(self.st, NOW + dt.timedelta(hours=1), boom), []); self.assertEqual(len(R.load(self.st)), 1)

    def test_post_command(self):
        seen = []
        it = {"to": "person", "text": "stand up", "thread": "t9"}
        R.post_as_remind(it, run=lambda cmd, **k: seen.append((cmd, k["input"])))
        self.assertEqual(seen[0][0][-4:], ["--as", "remind", "--thread", "t9"]); self.assertEqual(seen[0][1], "@person stand up")
        with self.assertRaises(SystemExit): R.post_as_remind({**it, "text": "@rootwarden hi"}, run=lambda *a, **k: None)

    def test_needs_a_thread_and_a_cap(self):
        with self.assertRaises(SystemExit): R.add("at", "+1h", "x", store=self.st, now=NOW, thread=None)
        for _ in range(R.MAX_ITEMS): self.add("at", "+1h", "x")
        with self.assertRaises(SystemExit): self.add("at", "+1h", "x")


if __name__ == "__main__": unittest.main()
