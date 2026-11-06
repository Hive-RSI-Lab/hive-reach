// WhatsApp bridge (Baileys), run by connector.py. Line-delimited JSON on stdin/stdout. It never prints a message that is not in the
// person's own self-chat: the jid check comes before anything else in the message is read.
//   out: {t:"ready",me,lid} {t:"msg",id,chat,text,files:[path]} {t:"sent",ref,id} {t:"error",ref,why} {t:"closed"}
//   in:  {t:"send",ref,id,text,files:[path]}
// Env: WA_SESSION (auth folder, mode 700), WA_INBOX (where the person's own attachments land). `--link` shows a QR and exits.
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { pathToFileURL } from "node:url";

export const OUT_PREFIX = "H2";            // ids of what we send; its echo carries the same id
export const MAX_MEDIA = 50 * 2 ** 20;

// "46701234567:12@s.whatsapp.net" -> "46701234567@s.whatsapp.net"; the "@lid" form keeps its own server part
export function normJid(j) {
  if (typeof j !== "string") return "";
  const [user, server] = j.split("@");
  if (!user || !server) return "";
  return `${user.split(":")[0].split("_")[0]}@${server}`;
}

// own: this account's jids, any form (phone and lid)
export function isSelfChat(remoteJid, own) {
  const j = normJid(remoteJid);
  return j !== "" && !j.endsWith("@g.us") && !j.endsWith("@broadcast") && own.map(normJid).filter(Boolean).includes(j);
}

export const isOwnEcho = (id) => typeof id === "string" && id.startsWith(OUT_PREFIX);

// The one gate for incoming. Gets the key only; the body is not looked at unless this says yes.
export function accept(key, own) {
  return !!key && isSelfChat(key.remoteJid, own) && !isOwnEcho(key.id);
}

const send = (o) => process.stdout.write(JSON.stringify(o) + "\n");

function textOf(m) {
  const x = m || {};
  return x.conversation || x.extendedTextMessage?.text || x.imageMessage?.caption || x.videoMessage?.caption || x.documentMessage?.caption || "";
}

async function saveMedia(baileys, msg, inbox) {
  const body = msg.message || {};
  for (const k of ["imageMessage", "documentMessage", "videoMessage", "audioMessage"]) {
    const part = body[k];
    if (!part) continue;
    if (Number(part.fileLength || 0) > MAX_MEDIA) return null;
    const name = (part.fileName || k.replace("Message", "")).replace(/[^\w.-]+/g, "_").replace(/^\.+/, "") || "file";
    const dir = fs.mkdtempSync(path.join(inbox, "wa-"));
    const file = path.join(dir, name);
    fs.writeFileSync(file, await baileys.downloadMediaMessage(msg, "buffer", {}));
    return file;
  }
  return null;
}

async function main() {
  const link = process.argv.includes("--link");
  const session = process.env.WA_SESSION;
  if (!session) throw new Error("WA_SESSION not set");
  const baileys = await import("@whiskeysockets/baileys");
  const makeWASocket = baileys.default?.default || baileys.default || baileys.makeWASocket;
  const { state, saveCreds } = await baileys.useMultiFileAuthState(session);
  let sock;
  const own = () => [sock?.user?.id, sock?.user?.lid].filter(Boolean);
  const quiet = { level: "silent", child() { return this; }, trace() {}, debug() {}, info() {}, warn() {}, error() {}, fatal() {} };

  const connect = () => {
    sock = makeWASocket({ auth: state, logger: quiet, printQRInTerminal: false, syncFullHistory: false, markOnlineOnConnect: false,
                          shouldSyncHistoryMessage: () => false });
    sock.ev.on("creds.update", saveCreds);
    sock.ev.on("connection.update", async (u) => {
      if (u.qr && link) (await import("qrcode-terminal")).default.generate(u.qr, { small: true }, (q) => process.stderr.write(q + "\n"));
      if (u.connection === "open") {
        send({ t: "ready", me: sock.user.id, lid: sock.user.lid || "" });
        if (link) setTimeout(() => process.exit(0), 3000);   // let the keys settle
      }
      if (u.connection === "close") {
        const code = u.lastDisconnect?.error?.output?.statusCode;
        if (code === baileys.DisconnectReason.loggedOut) { send({ t: "closed" }); process.exit(2); }
        setTimeout(connect, 3000);   // the usual restart after pairing, or a dropped connection; never a tight loop against WhatsApp
      }
    });
    if (link) return;   // linking needs no message handler at all
    sock.ev.on("messages.upsert", async ({ messages, type }) => {
      if (type !== "notify") return;   // history and backfill are not read
      for (const m of messages) {
        if (!accept(m.key, own())) continue;   // everything else: gone, unread
        const file = await saveMedia(baileys, m, process.env.WA_INBOX).catch(() => null);
        send({ t: "msg", id: m.key.id, chat: normJid(m.key.remoteJid), text: textOf(m.message), files: file ? [file] : [] });
      }
    });
  };
  connect();
  if (link) return;

  readline.createInterface({ input: process.stdin }).on("line", async (line) => {
    let r;
    try { r = JSON.parse(line); } catch { return; }
    if (r.t !== "send") return;
    try {
      const to = [sock.user.id].map(normJid)[0];   // always our own chat; nothing in the request chooses it
      const opts = { messageId: String(r.id) };
      if (!isOwnEcho(opts.messageId)) throw new Error("id not marked");
      if (r.text) await sock.sendMessage(to, { text: r.text }, opts);
      for (const f of r.files || []) await sock.sendMessage(to, { document: fs.readFileSync(f), fileName: path.basename(f), mimetype: "application/octet-stream" });
      send({ t: "sent", ref: r.ref });
    } catch (e) { send({ t: "error", ref: r.ref, why: "send failed" }); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { send({ t: "error", why: "bridge failed to start" }); process.exit(1); });
}
