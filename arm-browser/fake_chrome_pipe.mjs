// Tests only: stands in for the dash module's chrome_pipe.mjs where that module is not installed (CI).
// Same signature; starts the command with the same argv, waits for it to exit, then fails as the real one does when Chrome quits.
import { spawn } from "node:child_process";

export async function openChrome(args, { cmd = ["google-chrome"] } = {}) {
  const chrome = spawn(cmd[0], [...cmd.slice(1), "--remote-debugging-pipe", ...args], { stdio: "ignore" });
  const c = await new Promise(ok => { chrome.on("error", () => ok("error")); chrome.on("exit", ok); });
  throw Error(`Chrome exited (${c})`);
}
