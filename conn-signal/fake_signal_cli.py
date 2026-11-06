"""Stands in for `signal-cli ... jsonRpc`. Speaks the same line-delimited JSON-RPC on stdin/stdout. Everything it is asked is logged to FAKE_LOG."""
import json, os, sys, time
ME, OTHER = "+10000000001", "+10000000002"
log = open(os.environ["FAKE_LOG"], "a")

def out(o): sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
def env(ts, dest, text, atts=(), src=ME):
    return {"jsonrpc": "2.0", "method": "receive", "params": {"envelope": {"sourceNumber": src, "timestamp": ts, "syncMessage": {"sentMessage": {
        "destinationNumber": dest, "timestamp": ts, "message": text, "attachments": list(atts)}}}}}

out(env(1, OTHER, "SECRET-TO-OTHER", [{"id": "otherfile", "filename": "o.txt", "size": 3}]))
out({"jsonrpc": "2.0", "method": "receive", "params": {"envelope": {"sourceNumber": OTHER, "timestamp": 2, "dataMessage": {"message": "SECRET-FROM-OTHER"}}}})
out({"jsonrpc": "2.0", "method": "receive", "params": {"envelope": {"sourceNumber": ME, "timestamp": 3, "syncMessage": {"sentMessage": {"groupInfo": {"groupId": "g"}, "destinationNumber": ME, "message": "SECRET-GROUP"}}}}})
out(env(4, ME, "note to self", [{"id": "a1", "filename": "../n.txt", "size": 5}]))
for line in sys.stdin:
    req = json.loads(line); log.write(json.dumps([req["method"], req.get("params")]) + "\n"); log.flush()
    if req["method"] == "send":
        # the echo can race the answer: send it first for the second message
        if req["params"]["message"] == "race": out(env(900, ME, "race"))
        out({"jsonrpc": "2.0", "id": req["id"], "result": {"timestamp": 900 + len(req["params"]["message"])}})
        time.sleep(0.05)
        out(env(900 + len(req["params"]["message"]), ME, req["params"]["message"]))
    elif req["method"] == "getAttachment":
        out({"jsonrpc": "2.0", "id": req["id"], "result": {"data": "aGVsbG8="}})
    else:
        out({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -1, "message": "no"}})
