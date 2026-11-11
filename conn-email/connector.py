"""Email, through a mailbox made only for this (never the person's own: sending from theirs is limit 4). IMAP poll in, SMTP out, stdlib.
A From address is forgeable, so identity is two things: the sender is on the allow-list, and the mailbox's own server vouches for an aligned
DKIM pass in the Authentication-Results header it added. Mail that fails is dropped: no reply, no pairing code, nothing posted.
The parsing functions are pure (raw bytes in), and the IMAP/SMTP clients are injected, so tests need no sockets."""
import email, email.policy, email.utils, html.parser, imaplib, json, re, smtplib, ssl, sys, threading, time
from email.message import EmailMessage
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

POLL = 60
MAX_ATTACH = 10 * 2**20     # per file; a bigger one is named in the text instead
MAX_RAW = 40 * 2**20        # a whole message bigger than this is skipped
MAX_SEEN = 2000            # Message-IDs remembered, so re-sent signed mail is taken once
MAX_KNOWN = 500             # replies are remembered for this many verified senders
ROBOT_LOCALS = {"mailer-daemon", "postmaster", "no-reply", "noreply", "do-not-reply", "donotreply"}


# ---- pure parsing -------------------------------------------------------------------------------------
def bare(addr):
    """The lowercased address from a From value, or "" unless it is exactly one plain address."""
    pairs = email.utils.getaddresses([addr or ""])
    if len(pairs) != 1 or not re.fullmatch(r"[^\s<>,;\"()]+@[^\s<>,;\"()@]+\.[^\s<>,;\"()@]+", pairs[0][1]): return ""
    return pairs[0][1].lower()


def dkim_aligned(auth_headers, auth_server, from_addr):
    """True only when the FIRST Authentication-Results header (the one our own server put on top; senders can only add lower ones) names
    our authserv-id and has dkim=pass with header.d or header.i exactly the From domain (strict alignment: without the full public suffix list,
    relaxed alignment lets evil.me.uk sign for p@person.me.uk)."""
    if not auth_server or not auth_headers or not from_addr: return False
    text = re.sub(r"\([^()]*\)", " ", re.sub(r"\s+", " ", str(auth_headers[0])))  # comments out: "(dkim=pass)" is not a result
    parts = [s.strip() for s in text.split(";")]
    if (parts[0].split() or [""])[0].lower() != auth_server.lower(): return False
    want = from_addr.rsplit("@", 1)[1].lower()
    for seg in parts[1:]:
        if not re.match(r"dkim\s*=\s*pass\b", seg, re.I): continue
        for k, v in re.findall(r"header\.(d|i)\s*=\s*\"?([^\s\";]+)", seg, re.I):
            dom = v.rsplit("@", 1)[-1].lower()
            if dom == want: return True
    return False


def is_robot(msg, from_addr, own):
    """Mail we must never answer: auto-replies, lists, bulk, bounces, ourselves."""
    auto = (msg.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no": return "auto-submitted"
    if msg.get("List-Id") or msg.get("List-Unsubscribe"): return "list"
    if (msg.get("Precedence") or "").strip().lower() in ("bulk", "list", "junk", "auto_reply"): return "bulk"
    if (msg.get("X-Auto-Response-Suppress") or "").strip(): return "auto-response-suppressed"
    if (msg.get("Return-Path") or "").strip() == "<>": return "bounce"
    if from_addr.split("@")[0] in ROBOT_LOCALS or from_addr == own.lower(): return "robot sender"
    return ""


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "head", "title"}
    BREAK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "blockquote"}
    def __init__(self): super().__init__(convert_charrefs=True); self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        elif tag in self.BREAK: self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip = max(0, self.skip - 1)
        elif tag in self.BREAK: self.out.append("\n")
    def handle_data(self, d):
        if not self.skip: self.out.append(d)


def html_to_text(s):
    p = _Text()
    try: p.feed(s); p.close()
    except Exception: return re.sub(r"<[^>]*>", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", "".join(p.out)).strip()


WROTE = re.compile(r"^\s*On .{5,200}wrote:\s*$", re.S)
MARKERS = re.compile(r"^\s*(-{2,}\s*Original Message\s*-{2,}|_{10,}|-{5,}\s*Forwarded message\s*-{5,})\s*$", re.I)


def strip_quote(text):
    """Cut the quoted reply tail: an 'On ... wrote:' line, an Original Message rule, trailing '>' lines. If nothing is left, keep it all."""
    lines = text.replace("\r\n", "\n").split("\n")
    cut = len(lines)
    for i, ln in enumerate(lines):
        if MARKERS.match(ln) or WROTE.match(ln) or (ln.lstrip().startswith("On ") and i + 1 < len(lines) and WROTE.match(ln + " " + lines[i + 1].strip())):
            cut = i; break
    kept = lines[:cut]
    while kept and (not kept[-1].strip() or kept[-1].lstrip().startswith(">")): kept.pop()
    out = "\n".join(kept).strip()
    return out or text.strip()


def body_text(msg):
    """text/plain if there is one, else the HTML as plain text. Attachments are not body."""
    plain = html_ = None
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment": continue
        ctype = part.get_content_type()
        try: s = part.get_content()
        except Exception: continue
        if ctype == "text/plain" and plain is None: plain = s
        elif ctype == "text/html" and html_ is None: html_ = s
    return plain if plain is not None else html_to_text(html_ or "")


def attachments(msg, cap=MAX_ATTACH):
    """([(name, bytes)], [names too big or unreadable])"""
    got, skipped = [], []
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() != "attachment" and not part.get_filename(): continue
        name = part.get_filename() or "attachment"
        data = part.get_payload(decode=True) or b""
        (skipped if len(data) > cap else got).append(name if len(data) > cap else (name, data))
    return got, skipped


def inspect(raw, auth_server, own, cap=MAX_ATTACH):
    """Raw RFC822 bytes -> (parsed dict or None, why not). Pure. A message counts only if it is one clear sender, not a robot, and the
    first Authentication-Results header from our own server says an aligned DKIM pass."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    froms = msg.get_all("From") or []
    sender = bare(froms[0]) if len(froms) == 1 else ""
    if not sender: return None, "no single plain From"
    why = is_robot(msg, sender, own)
    if why: return None, why
    if not dkim_aligned(msg.get_all("Authentication-Results") or [], auth_server, sender): return None, "no aligned dkim pass"
    rcpt = {a.lower() for _, a in email.utils.getaddresses([str(v) for h in ("To", "Cc") for v in msg.get_all(h) or []])}
    if own and own.lower() not in rcpt: return None, "not addressed to this mailbox"  # signed mail meant for someone else, sent on to us
    files, big = attachments(msg, cap)
    text = strip_quote(body_text(msg))
    if big: text += "\n(attached files that were too big to take: " + ", ".join(big) + ")"
    refs = (msg.get("References") or "").split() + [x for x in [(msg.get("Message-ID") or "").strip()] if x]
    return {"sender": sender, "subject": str(msg.get("Subject") or "").strip(), "text": text, "message_id": (msg.get("Message-ID") or "").strip(),
            "references": refs[-10:], "files": files}, ""


def reply_subject(s):
    s = " ".join((s or "").split())
    return s if re.match(r"re:", s, re.I) else ("Re: " + s if s else "Re: (no subject)")


def build_reply(own, to, text, thread, files=()):
    """The outgoing message. Auto-Submitted stops other robots answering it. files: [(name, bytes)]."""
    m = EmailMessage(policy=email.policy.SMTP)
    m["From"], m["To"], m["Subject"] = own, to, reply_subject(thread.get("subject"))
    m["Auto-Submitted"] = "auto-replied"
    m["Message-ID"] = email.utils.make_msgid(domain=own.rsplit("@", 1)[-1])
    if thread.get("message_id"): m["In-Reply-To"] = thread["message_id"]
    if thread.get("references"): m["References"] = " ".join(thread["references"])
    m.set_content(text)
    for name, data in files: m.add_attachment(data, maintype="application", subtype="octet-stream", filename=name)
    return m


def uid_from_fetch(data):
    """The raw message from an imaplib fetch answer."""
    for item in data or []:
        if isinstance(item, tuple) and len(item) > 1: return item[1]
    return None


def tls():
    """A context that checks the server's certificate and name. Without one, imaplib and smtplib don't verify, and anyone on the
    path would be handed the app password at login."""
    return ssl.create_default_context()


# ---- the connector ----------------------------------------------------------------------------------
class Email(C.Connector):
    name = "email"; label = "email"; size = 8000

    def __init__(self, cfg=None, secret="", imap=None, smtp=None, sleep=time.sleep):
        super().__init__(cfg, secret)
        # allow_from goes through the bridge's allow-list (cfg["allow"]), as lowercased bare addresses
        allow = {bare(a) or str(a).strip().lower() for a in (self.cfg.get("allow_from") or []) + (self.cfg.get("allow") or [])}
        self.cfg["allow"] = sorted(allow)
        self.imap_factory = imap or (lambda: imaplib.IMAP4_SSL(self.cfg["imap_host"], int(self.cfg.get("imap_port", 993)), ssl_context=tls()))
        self.smtp_factory = smtp or self._smtp
        self.sleep, self.lock = sleep, threading.Lock()
        self.state_path = C.DATA / "email" / "state.json"

    def _smtp(self):
        port = int(self.cfg.get("smtp_port", 465))
        if port == 465: return smtplib.SMTP_SSL(self.cfg["smtp_host"], port, timeout=60, context=tls())
        s = smtplib.SMTP(self.cfg["smtp_host"], port, timeout=60); s.starttls(context=tls()); return s

    def ready(self):
        need = [k for k in ("imap_host", "smtp_host", "address", "auth_server") if not self.cfg.get(k)]
        if need: return "missing in the email config: " + ", ".join(need) + " (auth_server is the name your mailbox's server puts at the start of Authentication-Results)"
        if not self.secret: return "no app password: save it as conn-email with the dashboard's lock"
        return ""

    # state: last UID done, and who has written to us with a good DKIM pass (the only people we answer)
    def load(self):
        try: return json.loads(self.state_path.read_text())
        except (OSError, ValueError): return {}

    def save(self, st):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(st)); tmp.chmod(0o600); tmp.replace(self.state_path)

    def known(self, sender):
        """Allow-listed, or already paired (the bridge's own table). Only these get attachments saved to disk."""
        if sender in self.cfg["allow"]: return True
        try:
            db = C.open_db(C.DATA / "email")
            try: return bool(db.execute("select 1 from allow where sender=?", (sender,)).fetchone())
            finally: db.close()
        except Exception: return False

    # in
    def poll(self, box, inbound):
        """One pass over a logged-in IMAP session. Returns the number of messages handed on."""
        box.select("INBOX")
        validity = b"".join(x or b"" for x in (box.response("UIDVALIDITY")[1] or [])).decode() or "0"
        _, d = box.uid("search", None, "ALL")
        uids = sorted(int(u) for u in (d[0] or b"").split())
        st = self.load()
        if st.get("validity") != validity or "last" not in st:
            st.update(validity=validity, last=uids[-1] if uids else 0)  # first run: start at the newest, no history
            self.save(st); return 0
        n = 0
        for uid in [u for u in uids if u > st["last"]]:
            typ, data = box.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = uid_from_fetch(data) if typ == "OK" else None
            if raw is not None and len(raw) <= MAX_RAW: n += self.take(raw, f"{validity}-{uid}", inbound)
            st = self.load(); st["last"] = uid; self.save(st)  # by UID, so a crash never replays or skips
        return n

    def take(self, raw, mid, inbound):
        p, why = inspect(raw, self.cfg.get("auth_server", ""), self.cfg.get("address", ""), int(self.cfg.get("max_attachment", MAX_ATTACH)))
        if not p: return 0  # dropped silently: no reply, no code, no post
        st = self.load(); th = st.setdefault("threads", {})
        seen = st.setdefault("message_ids", [])
        if p["message_id"] and p["message_id"] in seen: return 0  # the same signed mail sent to us again
        if p["message_id"]: st["message_ids"] = (seen + [p["message_id"]])[-MAX_SEEN:]
        th[p["sender"]] = {"subject": p["subject"], "message_id": p["message_id"], "references": p["references"], "at": time.time()}
        for old in sorted(th, key=lambda k: th[k].get("at", 0))[:-MAX_KNOWN]: th.pop(old)
        self.save(st)
        paths = self.keep(p["files"]) if self.known(p["sender"]) else []
        text = (f"Subject: {p['subject']}\n\n" if p["subject"] else "") + p["text"]
        inbound(C.Msg(chat=p["sender"], sender=p["sender"], text=text, id=mid, dm=True, files=paths))
        return 1

    def keep(self, files):
        if not files: return []
        d = C.inbox_dir(self.name); out = []
        for name, data in files:
            f = d / (re.sub(r"[^\w.-]+", "_", name).lstrip(".") or "file"); f.write_bytes(data); out.append(f)
        return out

    def listen(self, inbound):
        while True:
            box = self.imap_factory()
            try:
                if box.login(self.cfg["address"], self.secret)[0] != "OK": raise RuntimeError("the mailbox refused the login")
                while True:
                    self.poll(box, inbound); self.sleep(int(self.cfg.get("poll", POLL)))
            except imaplib.IMAP4.error: raise RuntimeError("mailbox error (login or command refused)") from None  # no text that might hold the password
            finally:
                try: box.logout()
                except Exception: pass

    # out
    def send(self, chat, text, files=()):
        chat = str(chat).strip().lower()
        thread = self.load().get("threads", {}).get(chat)
        if thread is None or bare(chat) != chat:
            raise PermissionError("email only answers addresses that wrote in with a verified DKIM pass")
        data = []
        for f in files:
            b = Path(f).read_bytes()
            if len(b) <= int(self.cfg.get("max_attachment", MAX_ATTACH)): data.append((Path(f).name, b))
        msg = build_reply(self.cfg["address"], chat, text, thread, data)
        try:
            s = self.smtp_factory()
            try:
                s.login(self.cfg["address"], self.secret); s.send_message(msg)
            finally:
                try: s.quit()
                except Exception: pass
        except smtplib.SMTPAuthenticationError: raise RuntimeError("the mail server refused the login") from None
        except smtplib.SMTPException as e: raise RuntimeError(f"sending failed ({type(e).__name__})") from None


CONNECTOR = Email
