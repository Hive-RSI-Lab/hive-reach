"""iMessage, for a Mac the person is signed in on. The tower never talks to Apple: a small script on the Mac (mac_bridge.py) reads only the
person's own chat with themselves and swaps messages with the tower through a spool of files, over ssh on the tailscale network.
This side reads that spool. Only the self handle is accepted, both ways. The code only ever messages the person."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import conn as C
import spool as S

ECHO_WINDOW = 180  # seconds a message we sent can still come back as text in the chat
POLL = 1


class IMessage(C.Connector):
    name = "imessage"; label = "iMessage"; size = 4000
    self_chat_only = True; kind = "linked"

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.me = str(self.cfg.get("self") or "")
        self.spool = S.spool_dir(self.cfg)
        self.recent = []   # [text, sent_at, times_it_may_still_come_back]
        self.now = time.time

    def ready(self):
        if not self.me: return 'no handle: put your own iMessage phone number or email in ~/.config/h2/conn/imessage.json as "self"'
        if str(self.cfg["self"]).strip() != self.me or not S.norm_handle(self.me): return '"self" is not a usable phone number or email'
        if not self.spool.is_dir(): return "the spool isn't there yet: run `conn on imessage` once, then set up the Mac (see the README)"
        if self.spool.stat().st_mode & 0o077: return f"the spool at {self.spool} is readable by others: chmod 700 it"
        return ""

    def setup(self):
        S.ensure(self.spool)
        print("iMessage needs a script on your Mac: see the README. It reads only your chat with yourself.")
        return {"allow": [self.me], "home": self.me} if self.me else {}  # the person's own chat: no pairing

    def send(self, chat, text, files=()):
        if files: text = (text + "\n" if text else "") + "(files can't go over iMessage here: " + ", ".join(Path(f).name for f in files) + ")"
        if not text: return
        self.recent.append([text, self.now(), 2]); self.recent = self.recent[-50:]
        S.write(self.spool, "out", {"text": text})   # the Mac script sends it to the self handle it was started with, nothing in here picks the recipient

    def own_echo(self, text):
        now = self.now()
        self.recent = [r for r in self.recent if now - r[1] < ECHO_WINDOW and r[2] > 0]
        for r in self.recent:
            if r[0] == text: r[2] -= 1; return True
        return False

    def accept(self, obj):
        """The Msg for one spool file, or None. Anything not from the self handle is dropped before its text is looked at."""
        if not isinstance(obj, dict) or S.norm_handle(obj.get("handle")) != S.norm_handle(self.me): return None
        text = str(obj.get("text") or "")
        if self.own_echo(text): return None
        return C.Msg(chat=self.me, sender=self.me, text=text, id=str(obj.get("id") or time.time_ns()), dm=True, name="you")

    def listen(self, inbound):
        while True:
            for p in sorted((self.spool / "in").glob("*.json")):
                try: obj = json.loads(p.read_text())
                except (OSError, ValueError): obj = None
                m = self.accept(obj)
                if m: inbound(m)
                p.unlink(missing_ok=True)
            time.sleep(POLL)


CONNECTOR = IMessage
