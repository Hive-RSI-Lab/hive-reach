#!/usr/bin/env python3
"""Runs ON THE MAC the person is signed in to iMessage on. Not part of the tower's service; the person starts it.

  python3 mac_bridge.py --self +46701234567 --host person@tower-name   (tower-name is the tailscale name; ssh uses its own key)

What it does, and all it does:
  in:  reads ~/Library/Messages/chat.db read-only, ONLY the one-to-one chat with the --self handle, and sends new lines to the tower.
  out: takes lines the tower has for the person and sends them with osascript to the --self handle.
Other chats are never selected from the database, so their text never leaves sqlite. It listens on no port: it connects out to the tower
over ssh on tailscale. The Mac needs Full Disk Access for the terminal that runs this (System Settings > Privacy & Security).
Standard library only (the Mac's own python3 will do)."""
import argparse, json, re, sqlite3, subprocess, sys, time
from pathlib import Path

APPLE_EPOCH = 978307200   # chat.db counts from 2001-01-01
ECHO_WINDOW = 180         # seconds after sending that the same text coming back is our own echo
TWIN_WINDOW = 3           # a message to yourself can show up as two rows (sent and received); the second is dropped
DEFAULT_DB = Path.home() / "Library/Messages/chat.db"
DEFAULT_STATE = Path.home() / ".local/state/h2-imessage.json"
OSA = ['on run argv', 'tell application "Messages"', 'set svc to 1st account whose service type = iMessage',
       'send (item 1 of argv) to participant (item 2 of argv) of svc', 'end tell', 'end run']


def norm_handle(h):
    h = str(h or "").strip()
    if "@" in h: return h.lower()
    d = re.sub(r"[^\d+]", "", h)
    return "+" + d.lstrip("+") if d.lstrip("+") else ""


def open_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def self_chat_ids(db, me):
    """The chat(s) that are one-to-one (style 45) with the self handle. Reads chat names only, never a message."""
    me = norm_handle(me)
    if not me: return []
    return [r[0] for r in db.execute("select ROWID, chat_identifier from chat where style = 45") if norm_handle(r[1]) == me]


def body_text(text, blob):
    """The message text: the text column, or on newer macOS the NSString inside the attributedBody typedstream."""
    if text: return text
    if not blob: return ""
    i = blob.find(b"NSString")
    if i < 0: return ""
    b = bytes(blob[i + len(b"NSString") + 5:])   # five bytes of class preamble precede the length
    if not b: return ""
    if b[0] == 0x81: n, b = int.from_bytes(b[1:3], "little"), b[3:]
    else: n, b = b[0], b[1:]
    return b[:n].decode("utf-8", "replace")


def new_rows(db, me, after):
    """Messages in the self chat with ROWID > after: (rowid, text, from_me, epoch seconds, has_attachment). Nothing from any other chat."""
    ids = self_chat_ids(db, me)
    if not ids: return []
    q = ("select m.ROWID, m.text, m.attributedBody, m.is_from_me, m.date, m.cache_has_attachments from message m "
         "join chat_message_join j on j.message_id = m.ROWID where j.chat_id in (%s) and m.ROWID > ? and m.service = 'iMessage' order by m.ROWID" % ",".join("?" * len(ids)))
    out = []
    for rowid, text, blob, from_me, date, att in db.execute(q, [*ids, after]):
        secs = (date / 1e9 if date and date > 1e12 else date or 0) + APPLE_EPOCH
        out.append((rowid, body_text(text, blob), bool(from_me), secs, bool(att)))
    return out


def max_rowid(db):
    return db.execute("select coalesce(max(ROWID), 0) from message").fetchone()[0]


class Echo:
    """What this script sent comes back as rows in the self chat. Remember it, and drop the rows."""
    def __init__(self, now=time.time): self.sent, self.now = [], now
    def note(self, text): self.sent.append([text, self.now(), 2])
    def is_echo(self, text):
        t = self.now(); self.sent = [s for s in self.sent if t - s[1] < ECHO_WINDOW and s[2] > 0]
        for s in self.sent:
            if s[0] == text: s[2] -= 1; return True
        return False


class Bridge:
    def __init__(self, db, me, state_path, put, take, osa, now=time.time):
        self.db, self.me, self.state_path, self.put, self.take, self.osa = db, norm_handle(me), Path(state_path), put, take, osa
        self.echo, self.last_text, self.state = Echo(now), ("", 0.0), self.load()
        if self.state.get("rowid") is None: self.state["rowid"] = max_rowid(db); self.save()   # no replay of old messages

    def load(self):
        try: return json.loads(self.state_path.read_text())
        except (OSError, ValueError): return {}

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state)); self.state_path.chmod(0o600)

    def pump_in(self):
        for rowid, text, from_me, secs, att in new_rows(self.db, self.me, self.state["rowid"]):
            twin = text == self.last_text[0] and abs(secs - self.last_text[1]) <= TWIN_WINDOW
            if att and not text: text = "(an attachment was sent; attachments aren't forwarded)"
            if text and not twin and not self.echo.is_echo(text):
                self.put([json.dumps({"id": str(rowid), "handle": self.me, "text": text})])   # raises if the tower can't be reached: retried next round
            self.last_text = (text, secs)
            self.state["rowid"] = rowid; self.save()

    def pump_out(self):
        for line in self.take():
            text = str(json.loads(line).get("text") or "")
            if text: self.echo.note(text); self.osa(text, self.me)   # the recipient is always our own handle


def ssh(host, cmd, stdin=""):
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, cmd], input=stdin, capture_output=True, text=True, timeout=60)
    if r.returncode: raise RuntimeError("ssh to the tower failed")
    return r.stdout


def osascript(text, handle):
    subprocess.run(["osascript", *sum((["-e", l] for l in OSA), []), text, handle], check=True, capture_output=True, timeout=60)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self", required=True, dest="me"); ap.add_argument("--host", required=True)
    ap.add_argument("--db", default=str(DEFAULT_DB)); ap.add_argument("--state", default=str(DEFAULT_STATE))
    a = ap.parse_args()
    b = Bridge(open_ro(a.db), a.me, a.state, lambda ls: ssh(a.host, "put", "\n".join(ls) + "\n"),
               lambda: ssh(a.host, "take").splitlines(), osascript)
    while True:
        for step in (b.pump_in, b.pump_out):
            try: step()
            except Exception as e: print(f"{step.__name__}: {type(e).__name__}", file=sys.stderr, flush=True)   # no message text in the log
        time.sleep(3)


if __name__ == "__main__":
    main()
