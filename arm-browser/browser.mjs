#!/usr/bin/env node
// browser run URL [--steps FILE|-] [--max N]
//   Opens URL in headless Chrome with a brand-new throwaway profile, runs steps, prints page text labelled as untrusted data.
//   Steps (JSON list): {"op":"click","selector":"css"} {"op":"type","selector":"css","text":"..."} {"op":"wait","ms":500} {"op":"text"}
//   The profile is always a fresh temp dir, deleted afterwards. --user-data-dir is accepted only if it IS such a dir; no other Chrome flag passes through.
//   Typed text is whatever the caller gives; never type passwords or secrets (the person signs in nowhere from here).
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkHost, checkProfile, checkSteps, checkUrl, label, PREFIX } from "./guard.mjs";
import { lookup } from "node:dns/promises";

const args = process.argv.slice(2), cmd = args.shift();
const flag = n => { const i = args.indexOf(n); if (i < 0) return undefined; const v = args[i + 1]; args.splice(i, 2); return v; };
const die = (m, c = 2) => { console.error(m); process.exit(c); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36";

if (cmd !== "run") die("usage: browser run URL [--steps FILE|-] [--max N]");
let url, steps, dir, owned = false, maxChars = 20000;
try {
  let given = flag("--user-data-dir");
  const k = args.findIndex(a => a.startsWith("--user-data-dir="));
  if (k >= 0) { given = args[k].slice(16); args.splice(k, 1); }
  const stepsFile = flag("--steps"); maxChars = +(flag("--max") ?? 20000);
  const extra = args.filter(a => a.startsWith("-")); if (extra.length) throw Error(`refused: unknown option ${extra[0]}`);
  url = checkUrl(args[0] ?? "");
  await checkHost(url, lookup);
  steps = stepsFile ? checkSteps(JSON.parse(readFileSync(stepsFile === "-" ? 0 : stepsFile, "utf8"))) : [];
  if (given !== undefined) dir = checkProfile(given); else { dir = mkdtempSync(join(tmpdir(), PREFIX)); owned = true; }
} catch (e) { die(e.message); }

const cmdv = process.env.BROWSER_CHROME_CMD ? process.env.BROWSER_CHROME_CMD.split(" ") : ["google-chrome"]; // tests only
const { openChrome } = await import(process.env.BROWSER_PIPE || `${process.env.HOME}/modules/dash/web/test/chrome_pipe.mjs`);
let chrome, code = 0;
try {
  const o = await openChrome(["--headless=new", "--no-sandbox", "--disable-gpu", `--user-data-dir=${dir}`, `--user-agent=${UA}`, "--window-size=1280,1600", "about:blank"], { timeoutMs: 45000, cmd: cmdv });
  chrome = o.chrome; const send = o.send;
  const ev = async e => (await send("Runtime.evaluate", { expression: e, returnByValue: true })).result?.result?.value;
  const q = s => JSON.stringify(s);
  await send("Page.enable"); await send("Page.navigate", { url });
  for (let i = 0; i < 40; i++) { if ((await ev("document.readyState")) === "complete" && i > 0) break; await sleep(500); }
  const out = [];
  const read = async () => out.push(`# ${await ev("document.title")}\n# ${await ev("location.href")}\n\n${await ev("document.body ? document.body.innerText : ''")}`);
  for (const s of steps) {
    if (s.op === "click") await ev(`(()=>{const e=document.querySelector(${q(s.selector)});if(!e)throw Error('no such element');e.click()})()`);
    else if (s.op === "type") await ev(`(()=>{const e=document.querySelector(${q(s.selector)});if(!e)throw Error('no such element');e.focus();e.value=${q(String(s.text))};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))})()`);
    else if (s.op === "wait") await sleep(Math.min(+s.ms || 0, 10000));
    else if (s.op === "text") await read();
    await sleep(300);
  }
  if (!steps.length || steps.at(-1).op !== "text") await read();
  console.log(label(out.join("\n\n---\n\n"), maxChars));
} catch (e) { console.error("browser: " + e.message); code = 1; }
finally { try { chrome?.kill("SIGKILL"); } catch {} if (owned) rmSync(dir, { recursive: true, force: true }); }
process.exit(code);
