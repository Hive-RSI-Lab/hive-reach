"""Signal, on the person's own account, as a linked device (signal-cli over JSON-RPC). Only Note to Self is processed: every other
envelope is dropped on sight, before its text or files are read, stored or logged. The code only ever messages the person."""
import base64, binascii, json, queue, re, shutil, subprocess, sys, threading, time, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

MAX_ATTACH = 50 * 2**20
SEEN_KEEP = 500
BIN = Path.home() / ".local/share/signal-cli/bin/signal-cli"  # where link.py puts it


def norm(n): return re.sub(r"[\s()-]", "", str(n or ""))


def self_note(env, me, me_uuid=""):
    """The sentMessage if this envelope is the person's own device writing to their own number, else None.
    Only the sender and destination are looked at here; nothing else of a message that fails is touched."""
    if not isinstance(env, dict) or not me: return None
    src = norm(env.get("sourceNumber") or env.get("source"))
    if src and src != norm(me) and src != me_uuid: return None
    sync = env.get("syncMessage")
    sm = sync.get("sentMessage") if isinstance(sync, dict) else None
    if not isinstance(sm, dict): return None
    dest = norm(sm.get("destinationNumber") or sm.get("destination"))
    ok = dest == norm(me) or (me_uuid and (sm.get("destinationUuid") == me_uuid or dest == me_uuid))
    return sm if ok and "groupInfo" not in sm else None


class Signal(C.Connector):
    name = "signal"; label = "Signal"; size = 4000
    self_chat_only = True; kind = "linked"

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.me = norm(self.cfg.get("self"))
        self.session = Path(self.cfg.get("session") or C.SECRETS / "conn-signal-session")
        self.proc, self.waiting, self.wlock = None, {}, threading.Lock()
        self.sent, self.inflight, self.q = {}, [], queue.Queue()  # timestamps of what we sent, texts being sent right now

    def argv(self):
        if self.cfg.get("cmd"): return list(self.cfg["cmd"])
        return [str(BIN)] if BIN.exists() else [shutil.which("signal-cli") or str(BIN)]

    def ready(self):
        if not self.me: return 'no number: put your own Signal number in ~/.config/h2/conn/signal.json as "self": "+46..."'
        if str(self.cfg["self"]) != self.me: return 'write "self" with no spaces or dashes, like "+46701234567"'
        if not (Path(self.argv()[0]).exists() or shutil.which(self.argv()[0])):
            return "signal-cli isn't installed: run `python3 -I ~/modules/conn-signal/link.py` (it fetches it)"
        if not self.session.is_dir() or not any(self.session.iterdir()):
            return f"not linked yet: run `python3 -I ~/modules/conn-signal/link.py {self.me}` and scan the code"
        if self.session.stat().st_mode & 0o077: return f"the link session at {self.session} is readable by others: chmod 700 it"
        return ""

    def setup(self):
        print("Signal links as a second device on your own account. Run link.py, scan the code in Signal > Settings > Linked devices.")
        print("Only Note to Self is read; everything else the device could see is dropped. Read the README first.")
        return {"allow": [self.me], "home": self.me} if self.me else {}  # the person's own chat: no pairing

    # talking to signal-cli
    def call(self, method, params, timeout=60):
        proc = self.proc
        if not proc or proc.poll() is not None: raise RuntimeError("signal-cli isn't running")
        rid, ev, box = uuid.uuid4().hex, threading.Event(), {}
        self.waiting[rid] = (ev, box)
        try:
            with self.wlock:
                proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n"); proc.stdin.flush()
            if not ev.wait(timeout): raise RuntimeError(f"signal-cli didn't answer {method}")
        finally: self.waiting.pop(rid, None)
        if "error" in box: raise RuntimeError(f"signal-cli refused {method}")  # its message may hold a number: not repeated
        return box.get("result") or {}

    def send(self, chat, text, files=()):
        params = {"noteToSelf": True, "message": text or ""}  # always the person's own number, whatever `chat` said
        if files: params["attachments"] = [str(Path(f).resolve()) for f in files]
        if text: self.inflight.append(text)
        try:
            ts = self.call("send", params).get("timestamp")
        finally:
            if text and text in self.inflight: self.inflight.remove(text)
        if ts:
            self.sent[ts] = 1
            for k in list(self.sent)[:-SEEN_KEEP]: del self.sent[k]

    def own_echo(self, sm, env):
        """What we sent comes back as a sync message from the person's own device. Dropped here, or the hive would answer itself."""
        ts = sm.get("timestamp") or env.get("timestamp")
        return ts in self.sent or (bool(sm.get("message")) and sm["message"] in self.inflight)

    def read(self, proc):
        for line in proc.stdout:
            try: obj = json.loads(line)
            except ValueError: continue
            if not isinstance(obj, dict): continue
            if "id" in obj and ("result" in obj or "error" in obj):
                w = self.waiting.get(obj["id"])
                if w: w[1].update(obj); w[0].set()
                continue
            env = (obj.get("params") or {}).get("envelope") if obj.get("method") == "receive" else None
            sm = self_note(env, self.me, self.cfg.get("self_uuid", ""))
            if sm is not None and not self.own_echo(sm, env): self.q.put((sm, env))
        self.q.put(None)

    def fetch(self, sm):
        paths, failed = [], []
        for a in sm.get("attachments") or []:
            name = a.get("filename") or a.get("id") or "file"
            try:
                if (a.get("size") or 0) > MAX_ATTACH: raise RuntimeError("too big")
                data = base64.b64decode(self.call("getAttachment", {"id": a["id"], "recipient": self.me}, 120)["data"], validate=False)
                if len(data) > MAX_ATTACH: raise RuntimeError("too big")
                p = C.inbox_dir(self.name) / (re.sub(r"[^\w.-]+", "_", name).lstrip(".") or "file")
                p.write_bytes(data); paths.append(p)
            except (RuntimeError, KeyError, TypeError, binascii.Error, OSError):
                failed.append(name)
        return paths, failed

    def deliver(self, sm, env, inbound):
        text = sm.get("message") or ""
        files, failed = self.fetch(sm)
        if failed: text += "\n(attached files that couldn't be fetched: " + ", ".join(failed) + ")"
        ts = sm.get("timestamp") or env.get("timestamp")
        inbound(C.Msg(chat=self.me, sender=self.me, text=text, id=str(ts), dm=True, name="you", files=files))

    def listen(self, inbound):
        cmd = self.argv() + ["--config", str(self.session), "-a", self.me, "jsonRpc", "--ignore-attachments"]  # attachments only on request, below
        proc = self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        threading.Thread(target=self.read, args=(proc,), daemon=True).start()
        try:
            while True:
                try: item = self.q.get(timeout=1)
                except queue.Empty:
                    if proc.poll() is not None: raise RuntimeError("signal-cli stopped")
                    continue
                if item is None: raise RuntimeError("signal-cli stopped")
                self.deliver(*item, inbound)
        finally:
            proc.kill(); self.proc = None


CONNECTOR = Signal
