"""The tower's end of the Mac link: a spool of small JSON files, filled and emptied by the Mac script over ssh.
On the tower, put it behind a restricted key in authorized_keys (see the README), so the Mac can run `put` and `take` and nothing else:
  put   reads JSON lines from stdin (what the person wrote in their own iMessage chat) into in/
  take  prints and removes what the hive wants said (out/), one JSON line each
Only the person's own handle is kept; anything else is dropped here as well as on the Mac."""
import json, os, re, sys, time, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

MAX_LINE = 20_000
MAX_BATCH = 50


def norm_handle(h):
    """A phone number as +digits, an email lowercased; '' for nothing usable."""
    h = str(h or "").strip()
    if "@" in h: return h.lower()
    d = re.sub(r"[^\d+]", "", h)
    return "+" + d.lstrip("+") if d.lstrip("+") else ""


def spool_dir(cfg=None):
    return Path((cfg or {}).get("spool") or C.DATA / "imessage" / "spool")


def ensure(d):
    for sub in ("in", "out"): (Path(d) / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
    Path(d).chmod(0o700)


def write(d, sub, obj):
    """Written under a dotted name and renamed, so a reader never sees half a file."""
    name = f"{time.time_ns()}-{uuid.uuid4().hex[:6]}.json"
    tmp = Path(d) / sub / ("." + name)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(obj, f)
    tmp.rename(Path(d) / sub / name)


def put(lines, d, me):
    kept = 0
    for line in list(lines)[:MAX_BATCH]:
        if len(line) > MAX_LINE: continue
        try: o = json.loads(line)
        except ValueError: continue
        if not isinstance(o, dict) or norm_handle(o.get("handle")) != norm_handle(me): continue   # nothing else is kept
        write(d, "in", {"id": str(o.get("id") or ""), "handle": norm_handle(me), "text": str(o.get("text") or "")[:8000]})
        kept += 1
    return kept


def take(d):
    out = []
    for p in sorted((Path(d) / "out").glob("*.json"))[:MAX_BATCH]:
        try: out.append(json.loads(p.read_text())); p.unlink()
        except (OSError, ValueError): pass
    return out


def main(argv, stdin=sys.stdin, stdout=sys.stdout):
    cmd = (argv[1:] or os.environ.get("SSH_ORIGINAL_COMMAND", "").split())[:1]
    cfg = C.load_config("imessage"); me = cfg.get("self")
    if not me or cmd not in (["put"], ["take"]): return 2
    d = spool_dir(cfg); ensure(d)
    if cmd == ["put"]: put(stdin.read().splitlines(), d, me)
    else:
        for o in take(d): stdout.write(json.dumps({"text": str(o.get("text") or "")}) + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
