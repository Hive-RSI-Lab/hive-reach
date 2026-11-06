"""Telegram. Long poll, so no port. Identity is the fixed numeric user id; only private chats count."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

KINDS = ("document", "audio", "voice", "video", "video_note", "animation", "sticker")
MAX_DOWNLOAD = 20 * 2**20  # Bots can't fetch more than this


class Telegram(C.Connector):
    name = "telegram"; label = "Telegram"; size = 4000

    def __init__(self, cfg=None, secret=""):
        super().__init__(cfg, secret)
        self.base = self.cfg.get("api", "https://api.telegram.org").rstrip("/")
        self.offset = None

    def call(self, method, body=None, timeout=60, **kw):
        r = C.http("POST", f"{self.base}/bot{self.secret}/{method}", body=body if body is not None else {}, timeout=timeout, **kw)
        if not r.get("ok"): raise RuntimeError(f"{method}: {r.get('description', 'not ok')}")
        return r.get("result")

    def send(self, chat, text, files=()):
        if text: self.call("sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": True})
        for f in files:
            body, ctype = C.multipart({"chat_id": chat}, [("document", f)])
            self.call("sendDocument", body, timeout=300, headers={"Content-Type": ctype})

    def fetch(self, msg):
        """A message's attachments, in a temp folder. One that can't be fetched is named in the text rather than lost silently."""
        wanted = []
        if msg.get("photo"): wanted.append((msg["photo"][-1], "photo.jpg"))
        for k in KINDS:
            if msg.get(k): wanted.append((msg[k], msg[k].get("file_name") or k))
        paths, failed = [], []
        for f, name in wanted:
            try:
                if (f.get("file_size") or 0) > MAX_DOWNLOAD: raise RuntimeError("too big")
                info = self.call("getFile", {"file_id": f["file_id"]})
                paths.append(C.download(f"{self.base}/file/bot{self.secret}/{info['file_path']}", C.inbox_dir(self.name), name))
            except Exception:
                failed.append(name)
        return paths, failed

    def handle(self, update, inbound):
        msg = update.get("message")
        if not msg: return  # edits, channel posts, joins: not a message to us
        chat, who = msg.get("chat") or {}, msg.get("from") or {}
        if not who.get("id") or who.get("is_bot"): return
        private = chat.get("type") == "private"
        text = msg.get("text") or msg.get("caption") or ""
        files, failed = self.fetch(msg) if private and self.trusted(who["id"]) else ([], [])  # a stranger's files never reach the disk
        if failed: text += "\n(attached files that couldn't be fetched: " + ", ".join(failed) + ")"
        inbound(C.Msg(chat=str(chat.get("id")), sender=str(who["id"]), text=text, id=str(update["update_id"]), dm=private,
                      name=who.get("username") or who.get("first_name") or "", files=files))

    def listen(self, inbound):
        while True:
            body = {"timeout": 30, "allowed_updates": ["message"]}
            if self.offset is not None: body["offset"] = self.offset
            for u in self.call("getUpdates", body, timeout=45) or []:
                self.offset = u["update_id"] + 1
                self.handle(u, inbound)


CONNECTOR = Telegram
