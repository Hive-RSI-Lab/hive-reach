"""Links H2 to the person's WhatsApp as a device. Run by the person: python3 -I link.py
Installs the Baileys bridge into this folder with npm (once), shows a QR code to scan in WhatsApp > Linked devices, and keeps the
session in ~/.config/h2/secrets/conn-whatsapp-session (mode 700). Read the README first: unofficial clients can get a number banned."""
import json, os, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "conn"))
import conn as C

HERE = Path(__file__).resolve().parent
PKGS = ["@whiskeysockets/baileys@7.0.0-rc14", "qrcode-terminal@0.12.0"]  # checked against this version: exports only, not a live link


def install():
    if (HERE / "node_modules/@whiskeysockets/baileys").is_dir(): return
    if not shutil.which("npm"): sys.exit("npm isn't installed")
    print("Installing the WhatsApp bridge (npm) into", HERE)
    subprocess.run(["npm", "install", "--save-exact", "--no-fund", "--no-audit", "--prefix", str(HERE), *PKGS], check=True)


def main():
    if input("Linking lets this computer see all your WhatsApp chats; only Message Yourself is read. Unofficial clients can get\n"
             "a number banned (a spare number is safer). Continue? [y/N] ").strip().lower() != "y": sys.exit("Not linked.")
    install()
    session = C.SECRETS / "conn-whatsapp-session"
    session.mkdir(parents=True, exist_ok=True, mode=0o700); session.chmod(0o700)
    env = {**os.environ, "WA_SESSION": str(session), "WA_INBOX": str(HERE)}
    print("In WhatsApp: Settings > Linked devices > Link a device, then scan the code below.")
    p = subprocess.Popen(["node", str(HERE / "bridge.mjs"), "--link"], stdout=subprocess.PIPE, text=True, env=env)  # the QR comes on stderr
    me = ""
    for line in p.stdout:
        try: o = json.loads(line)
        except ValueError: continue
        if o.get("t") == "ready": me = o["me"].split("@")[0].split(":")[0]
    if p.wait() or not me: sys.exit("linking didn't finish; run this again")
    C.save_allow("whatsapp", C.load_config("whatsapp") | {"self": me})
    print(f"Linked as {me}. Now: conn on whatsapp")


if __name__ == "__main__":
    main()
