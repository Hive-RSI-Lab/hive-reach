#!/usr/bin/env python3
"""conn: the connectors. `conn list` shows each and what it still needs. README.md explains the rest."""
import argparse, importlib.util, json, os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import conn as C  # noqa: E402

MODULES = HERE.parent
UNITS = C.HOME / ".config/systemd/user"
UNIT = "conn@{}.service"


def manifest(name):
    try: return json.loads((MODULES / f"conn-{name}" / "module.json").read_text())
    except (OSError, ValueError): return None


def names():
    return sorted(d.name[5:] for d in MODULES.glob("conn-*/") if (d / "module.json").exists())


def need(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or manifest(name) is None: sys.exit(f"conn: no connector called {name}; see conn list")
    return manifest(name)


def load(name):
    """The connector's class, built with its config and its token."""
    need(name)
    f = MODULES / f"conn-{name}" / "connector.py"
    spec = importlib.util.spec_from_file_location(f"connector_{name.replace('-', '_')}", f)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.CONNECTOR(C.load_config(name), C.read_secret(name))


def bridge(name):
    c = load(name)
    return C.Bridge(name, c.send, c.cfg, size=c.size, label=c.label, audit=C.audit_post, cfg_fn=lambda: C.load_config(name))


def systemctl(*a): return subprocess.run(["systemctl", "--user", *a], capture_output=True, text=True)


def state(name):
    return systemctl("is-active", UNIT.format(name)).stdout.strip() or "unknown"


def cmd_list(a):
    for n in names():
        m = manifest(n)
        try: missing = load(n).ready()
        except ImportError as e: missing = f"package {e.name} comes with the service, can't check here"
        except Exception as e: missing = f"can't load: {type(e).__name__}: {e}"
        st = state(n)
        print(f"{n:<14} {st:<9} {missing or 'ready'}" + (f"  [{m['kind']}]" if m.get("kind") else ""))


def cmd_run(a):
    m = need(a.name)
    pkgs = m.get("python") or []
    if pkgs and not os.environ.get("CONN_DEPS"):  # a connector that needs a package: uv fetches it once and keeps it away from the system
        os.environ["CONN_DEPS"] = "1"
        cmd = ["uv", "run", "--quiet", "--no-project", "--python", "3.12"]
        for p in pkgs: cmd += ["--with", p]
        os.execvp("uv", cmd + ["python", "-I", str(HERE / "conn_cli.py"), "run", a.name])
    c = load(a.name)
    missing = c.ready()
    if missing: sys.exit(f"conn {a.name}: {missing}")
    C.run(c, log=lambda s: print(s, flush=True))


def cmd_ready(a):
    missing = load(a.name).ready()
    if missing: sys.exit(f"conn {a.name}: {missing}")


def cmd_on(a):
    c = load(a.name)
    changes = c.setup() or {}
    if changes:
        C.save_allow(a.name, C.load_config(a.name) | changes, by=f"`conn on {a.name}`"); c = load(a.name)
    missing = c.ready()
    if missing: sys.exit(f"conn {a.name}: {missing}")
    UNITS.mkdir(parents=True, exist_ok=True)
    link = UNITS / "conn@.service"
    link.unlink(missing_ok=True); link.symlink_to(HERE / "conn@.service")
    systemctl("daemon-reload")
    r = systemctl("enable", "--now", UNIT.format(a.name))
    if r.returncode: sys.exit(f"conn {a.name}: {r.stderr.strip()}")
    print(f"{a.name} is on. `conn log {a.name}` shows how it's doing.")


def cmd_off(a):
    need(a.name); systemctl("disable", "--now", UNIT.format(a.name)); print(f"{a.name} is off.")


def cmd_log(a):
    need(a.name)
    print(subprocess.run(["journalctl", "--user", "-u", UNIT.format(a.name), "-n", str(a.n), "--no-pager", "-o", "cat"], capture_output=True, text=True).stdout)


PERSON_KEYS = {"allow_from", "self", "person_number", "enabled", "allow_http"}  # who may talk, who is "the person", whether texting is on, a login in the clear


def person_only(what):
    """Only the person approves who may talk: on the dash (`pair NAME CODE`), or in a shell of their own. Agents have H2_NAME set."""
    if os.environ.get("H2_NAME"): sys.exit(f"conn {what}: only the person can do this, by typing `pair NAME CODE` on the dashboard.")


def cmd_pair(a):
    person_only("pair"); need(a.name)
    b = bridge(a.name)
    who = b.pair(a.code)
    if not who: sys.exit("no such code, or it's over an hour old. Have them send the bot another message after the hour, for a new code.")
    print(f"paired {who} on {a.name}. They'll be told as soon as the service sends it.")


def cmd_allow(a):
    person_only("allow"); need(a.name); bridge(a.name).allow(a.id); print(f"{a.id} may now talk to {a.name}")


def cmd_accept(a):
    person_only("accept"); need(a.name); bridge(a.name).accept(); print(f"{a.name}: the list as it stands is now what's expected")


def cmd_deny(a):
    need(a.name); bridge(a.name).deny(a.id, by=os.environ.get("H2_NAME") or "a shell"); print(f"{a.id} is off {a.name}")


def cmd_who(a):
    need(a.name); b = bridge(a.name)
    for r in b.db.execute("select * from allow"): print(f"allowed {r['sender']} {r['name'] or ''}")
    for s in b.cfg.get("allow") or []: print(f"allowed {s} (config)")
    added, gone = b.allow_diff()
    if added or gone: print(f"NOT WHAT WAS PAIRED: {b.diff_words(added, gone)}. Check it, then `conn accept {a.name}` from your own shell if it's right.")
    for r in b.db.execute("select sender, name, at from pending"): print(f"waiting {r['sender']} {r['name'] or ''} since {time.strftime('%H:%M', time.gmtime(r['at']))} UTC")
    print("home:", b.home() or "(none yet)")


def cmd_send(a):
    """Queue a message to the person's home chat on this connector. The service delivers it; if it's off, it waits."""
    need(a.name); b = bridge(a.name)
    home = b.home()
    if not home: sys.exit(f"{a.name} has no home chat yet: pair one first")
    text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
    files = []
    for f in a.file or []:
        p = Path(f).resolve()
        if not p.is_relative_to(C.FILES.resolve()) or not p.is_file(): sys.exit(f"{f}: only files under ~/files go out")
        files.append(p)
    b.enqueue({}, home, C.plain_out(text), files)
    if state(a.name) != "active": print(f"queued, but {a.name} isn't running: `conn on {a.name}`")
    else: print("queued")


def cmd_set(a):
    need(a.name); cfg = C.load_config(a.name)
    if len(a.pairs) == 2 and "=" not in a.pairs[0]: a.pairs = ["=".join(a.pairs)]  # `conn set irc server x` as well as `server=x`
    for kv in a.pairs:
        k, _, v = kv.partition("=")
        if k == "allow": sys.exit("use conn allow or a pairing")
        if k in PERSON_KEYS: person_only(f"set {k}")
        try: cfg[k] = json.loads(v)
        except ValueError: cfg[k] = v
    (C.save_allow if any(kv.partition("=")[0] in PERSON_KEYS for kv in a.pairs) else C.save_config)(a.name, cfg)
    print(f"{a.name}: saved. `systemctl --user restart {UNIT.format(a.name)}` if it's running.")


def cmd_test(a):
    bad = 0
    for d in [HERE] + [MODULES / f"conn-{n}" for n in names()]:
        for t in sorted(d.glob("test_*.py")):
            r = subprocess.run([sys.executable, "-I", str(t)], capture_output=True, text=True)
            tail = (r.stderr.strip().splitlines() or [""])[-1]
            print(f"{'ok  ' if not r.returncode else 'FAIL'} {t.parent.name}/{t.name}: {tail}")
            bad += bool(r.returncode)
    sys.exit(bad and 1)


p = argparse.ArgumentParser(prog="conn", description=__doc__)
s = p.add_subparsers(dest="cmd", required=True)
s.add_parser("list").set_defaults(fn=cmd_list)
s.add_parser("test").set_defaults(fn=cmd_test)
for n, f in (("run", cmd_run), ("ready", cmd_ready), ("on", cmd_on), ("off", cmd_off), ("who", cmd_who)):
    q = s.add_parser(n); q.add_argument("name"); q.set_defaults(fn=f)
q = s.add_parser("log"); q.add_argument("name"); q.add_argument("-n", type=int, default=30); q.set_defaults(fn=cmd_log)
q = s.add_parser("pair"); q.add_argument("name"); q.add_argument("code"); q.set_defaults(fn=cmd_pair)
for n, f in (("allow", cmd_allow), ("deny", cmd_deny)):
    q = s.add_parser(n); q.add_argument("name"); q.add_argument("id"); q.set_defaults(fn=f)
q = s.add_parser("send"); q.add_argument("name"); q.add_argument("text", nargs="+"); q.add_argument("--file", action="append"); q.set_defaults(fn=cmd_send)
q = s.add_parser("accept"); q.add_argument("name"); q.set_defaults(fn=cmd_accept)
q = s.add_parser("set"); q.add_argument("name"); q.add_argument("pairs", nargs="+"); q.set_defaults(fn=cmd_set)

if __name__ == "__main__":
    a = p.parse_args(); a.fn(a)
