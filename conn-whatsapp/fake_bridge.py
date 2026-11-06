"""Stands in for bridge.mjs: same line-delimited JSON. Prints a mix of self-chat and other-chat messages, and echoes what it is told to send."""
import json, os, sys
SELF = "46701234567@s.whatsapp.net"
INBOX = os.environ["WA_INBOX"]
def out(o): sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
open(os.path.join(INBOX, "doc.txt"), "w").write("hello")
OUTSIDE = os.path.join(os.path.dirname(INBOX), "outside.txt"); open(OUTSIDE, "w").write("x")
out({"t": "ready", "me": "46701234567:3@s.whatsapp.net", "lid": "99887766@lid"})
out({"t": "msg", "id": "1", "chat": "46709999999@s.whatsapp.net", "text": "SECRET-OTHER", "files": []})
out({"t": "msg", "id": "2", "chat": "12036@g.us", "text": "SECRET-GROUP", "files": []})
out({"t": "msg", "id": "3", "chat": SELF, "text": "note to self", "files": [os.path.join(INBOX, "doc.txt"), OUTSIDE]})
out({"t": "msg", "id": "4", "chat": "99887766@lid", "text": "via lid", "files": []})
for line in sys.stdin:
    r = json.loads(line)
    if r["t"] != "send": continue
    open(os.environ["FAKE_LOG"], "a").write(line)
    out({"t": "sent", "ref": r["ref"]})
    out({"t": "msg", "id": r["id"], "chat": SELF, "text": r["text"], "files": []})   # the echo, with our id
    out({"t": "msg", "id": "5", "chat": SELF, "text": "after echo", "files": []})
