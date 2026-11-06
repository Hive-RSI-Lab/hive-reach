"""Links H2 to the person's Signal as a second device. Run by the person: python3 -I link.py +46701234567
Fetches signal-cli (the official AsamK/signal-cli GitHub release, checked against GitHub's published sha256) if it isn't there,
shows the link as a QR code and text, and keeps the session in ~/.config/h2/secrets/conn-signal-session (mode 700)."""
import hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

API = "https://api.github.com/repos/AsamK/signal-cli/releases/latest"
SHARE = Path.home() / ".local/share"


def pick_asset(release):
    """The plain Java build (signal-cli-X.Y.Z.tar.gz), not the native or the signature."""
    for a in release.get("assets", []):
        n = a.get("name", "")
        if n == f"signal-cli-{release.get('tag_name', '').lstrip('v')}.tar.gz": return a
    raise SystemExit("couldn't find the signal-cli release file; see https://github.com/AsamK/signal-cli/releases")


def fetch_release():
    print("Fetching signal-cli from github.com/AsamK/signal-cli ...")
    rel = json.load(urllib.request.urlopen(urllib.request.Request(API, headers={"User-Agent": "h2-link"}), timeout=30))
    a = pick_asset(rel)
    tmp = Path(tempfile.mkdtemp(prefix="signal-cli-dl-"))  # its own empty folder
    tgz = tmp / a["name"]
    with urllib.request.urlopen(a["browser_download_url"], timeout=300) as r, tgz.open("wb") as f: shutil.copyfileobj(r, f)
    want = (a.get("digest") or "").removeprefix("sha256:")
    if want and hashlib.sha256(tgz.read_bytes()).hexdigest() != want: raise SystemExit("the download doesn't match GitHub's checksum; not using it")
    if not want: print("(GitHub gave no checksum for this file; it came over https from the official repository.)")
    with tarfile.open(tgz) as t: t.extractall(tmp / "x", filter="data")
    top = next((tmp / "x").iterdir())
    dest = SHARE / top.name
    if dest.exists(): shutil.rmtree(dest)
    SHARE.mkdir(parents=True, exist_ok=True); shutil.move(str(top), dest)
    cur = SHARE / "signal-cli"
    cur.unlink(missing_ok=True); cur.symlink_to(dest)
    shutil.rmtree(tmp, ignore_errors=True)


def show(uri):
    print("\nIn Signal on your phone: Settings > Linked devices > Link new device, then scan this:\n")
    if shutil.which("qrencode"): subprocess.run(["qrencode", "-t", "ANSIUTF8", uri])
    else: print("(install qrencode to see a QR code here; otherwise turn the text below into a QR code yourself)")
    print("\n" + uri + "\n")


def main():
    if len(sys.argv) != 2 or not sys.argv[1].startswith("+"):
        sys.exit("usage: link.py +yournumber   (your own Signal number, with country code)")
    me = sys.argv[1]
    if not (SHARE / "signal-cli/bin/signal-cli").exists(): fetch_release()
    session = C.SECRETS / "conn-signal-session"
    session.mkdir(parents=True, exist_ok=True, mode=0o700); session.chmod(0o700)
    p = subprocess.Popen([str(SHARE / "signal-cli/bin/signal-cli"), "--config", str(session), "link", "-n", "H2"], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        if line.startswith(("sgnl://", "tsdevice:")): show(line.strip())  # the link is a one-time secret: shown, not saved
    if p.wait(): sys.exit("linking didn't finish; run this again")
    C.save_allow("signal", C.load_config("signal") | {"self": me})
    print("Linked. Now: conn on signal")


if __name__ == "__main__":
    main()
