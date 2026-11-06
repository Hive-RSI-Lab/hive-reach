"""WhatsApp, on the person's own account, as a linked device (a Baileys bridge in Node). Only the Message Yourself chat is processed:
everything else is dropped in the bridge before it is printed, and again here before it is stored, logged or parsed further.
The code only ever messages the person."""
import json, queue, re, secrets as pysecrets, shutil, subprocess, sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

HERE = Path(__file__).resolve().parent
OUT_PREFIX = "H2"  # ids of what we send; the echo of it comes back with the same id


def norm_jid(j):
    """'4670123:12@s.whatsapp.net' -> '4670123@s.whatsapp.net'. '' for anything that isn't a user@server."""
    if not isinstance(j, str) or j.count("@") != 1: return ""
    user, server = j.split("@")
    user = user.split(":")[0].split("_")[0]
    return f"{user}@{server}" if user and server else ""


def self_jids(me, *more):
    """A bare number, or a jid, as the account's own jids (phone form, plus a lid form if known)."""
    out = []
    for x in (me, *more):
        x = str(x or "").strip()
        if x and "@" not in x: x = re.sub(r"\D", "", x) + "@s.whatsapp.net"
        if norm_jid(x): out.append(norm_jid(x))
    return out


def is_self_chat(chat, own):
    j = norm_jid(chat)
    return bool(j) and not j.endswith(("@g.us", "@broadcast")) and j in own


def new_id(): return OUT_PREFIX + pysecrets.token_hex(8).upper()
def is_own_echo(i): return isinstance(i, str) and i.startswith(OUT_PREFIX)


class WhatsApp(C.Connector):
    name = "whatsapp"; label = "WhatsApp"; size = 4000
    self_chat_only = True; kind = "linked"

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.me = str(self.cfg.get("self") or "")  # as configured: the base compares chat ids to this
        self.lid = self.cfg.get("self_lid", "")
        self.session = Path(self.cfg.get("session") or C.SECRETS / "conn-whatsapp-session")
        self.proc, self.waiting, self.wlock, self.q = None, {}, threading.Lock(), queue.Queue()

    def own(self): return self_jids(self.cfg.get("self"), self.lid)

    def argv(self):
        return list(self.cfg["cmd"]) if self.cfg.get("cmd") else [shutil.which("node") or "node", str(HERE / "bridge.mjs")]

    def ready(self):
        if not self.me: return 'no number: put your own WhatsApp number in ~/.config/h2/conn/whatsapp.json as "self": "46701234567"'
        if not self.cfg.get("cmd") and not (HERE / "node_modules/@whiskeysockets").is_dir():
            return "the WhatsApp bridge isn't installed: run `python3 -I ~/modules/conn-whatsapp/link.py` (read the README first)"
        if not self.session.is_dir() or not any(self.session.iterdir()):
            return "not linked yet: run `python3 -I ~/modules/conn-whatsapp/link.py` and scan the code"
        if self.session.stat().st_mode & 0o077: return f"the link session at {self.session} is readable by others: chmod 700 it"
        return ""

    def setup(self):
        print("WhatsApp links as a device on your own account. Read the README first: it can see all your chats (only Message Yourself is read),")
        print("and unofficial clients can get a number banned; consider a spare number. Then run link.py and scan the code.")
        return {"allow": [self.me], "home": self.me} if self.me else {}  # the person's own chat: no pairing

    def call(self, req, timeout=120):
        proc = self.proc
        if not proc or proc.poll() is not None: raise RuntimeError("the WhatsApp bridge isn't running")
        ref, ev, box = pysecrets.token_hex(6), threading.Event(), {}
        self.waiting[ref] = (ev, box)
        try:
            with self.wlock:
                proc.stdin.write(json.dumps(req | {"ref": ref}) + "\n"); proc.stdin.flush()
            if not ev.wait(timeout): raise RuntimeError("the WhatsApp bridge didn't answer")
        finally: self.waiting.pop(ref, None)
        if box.get("t") == "error": raise RuntimeError("the WhatsApp bridge couldn't send")
        return box

    def send(self, chat, text, files=()):
        # the bridge sends to its own account whatever it is asked; the id marks the message so its echo is recognised
        self.call({"t": "send", "id": new_id(), "text": text or "", "files": [str(Path(f).resolve()) for f in files]})

    def accept(self, obj, inbox=None):
        """The Msg for a line from the bridge, or None. The chat is checked first; for anything else nothing more is read."""
        if not isinstance(obj, dict) or obj.get("t") != "msg": return None
        if not is_self_chat(obj.get("chat"), self.own()) or is_own_echo(obj.get("id")): return None
        inbox = Path(inbox or C.DATA / self.name / "incoming").resolve()
        files = [Path(f) for f in obj.get("files") or [] if isinstance(f, str) and Path(f).resolve().is_relative_to(inbox)]
        return C.Msg(chat=self.me, sender=self.me, text=str(obj.get("text") or ""), id=str(obj.get("id")), dm=True, name="you", files=files)

    def read(self, proc):
        for line in proc.stdout:
            try: obj = json.loads(line)
            except ValueError: continue
            if not isinstance(obj, dict): continue
            t = obj.get("t")
            if t in ("sent", "error") and obj.get("ref") in self.waiting:
                w = self.waiting[obj["ref"]]; w[1].update(obj); w[0].set()
            elif t == "ready" and not self.lid and obj.get("lid"): self.lid = str(obj["lid"])  # our own lid, from our own login
            elif t == "msg":
                m = self.accept(obj)
                if m: self.q.put(m)
        self.q.put(None)

    def listen(self, inbound):
        inbox = C.DATA / self.name / "incoming"; inbox.mkdir(parents=True, exist_ok=True)
        env = {**__import__("os").environ, "WA_SESSION": str(self.session), "WA_INBOX": str(inbox)}
        proc = self.proc = subprocess.Popen(self.argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        threading.Thread(target=self.read, args=(proc,), daemon=True).start()
        try:
            while True:
                try: m = self.q.get(timeout=1)
                except queue.Empty:
                    if proc.poll() is not None: raise RuntimeError("the WhatsApp bridge stopped")
                    continue
                if m is None: raise RuntimeError("the WhatsApp bridge stopped")
                inbound(m)
        finally:
            proc.kill(); self.proc = None


CONNECTOR = WhatsApp
