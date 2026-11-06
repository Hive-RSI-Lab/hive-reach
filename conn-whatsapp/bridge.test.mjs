import test from "node:test";
import assert from "node:assert/strict";
import { normJid, isSelfChat, accept, isOwnEcho } from "./bridge.mjs";

const own = ["46701234567:7@s.whatsapp.net", "99887766@lid"];
test("self chat in phone, device and lid forms", () => {
  assert.ok(isSelfChat("46701234567@s.whatsapp.net", own));
  assert.ok(isSelfChat("46701234567:3@s.whatsapp.net", own));
  assert.ok(isSelfChat("99887766@lid", own));
  assert.ok(isSelfChat("99887766:2@lid", own));
});
test("everything else is not", () => {
  for (const j of ["46709999999@s.whatsapp.net", "12036@g.us", "status@broadcast", "", undefined, null, "46701234567", "@s.whatsapp.net", "46701234567@g.us"])
    assert.ok(!isSelfChat(j, own), String(j));
  assert.ok(!isSelfChat("46701234567@s.whatsapp.net", []));
});
test("own echo is dropped, the person's message is not", () => {
  assert.ok(isOwnEcho("H2ABC"));
  assert.ok(!accept({ remoteJid: "46701234567@s.whatsapp.net", id: "H2ABC" }, own));
  assert.ok(accept({ remoteJid: "46701234567@s.whatsapp.net", id: "3EB0AA" }, own));
  assert.ok(!accept({ remoteJid: "46709999999@s.whatsapp.net", id: "3EB0AA" }, own));
  assert.ok(!accept(undefined, own));
});
test("normJid", () => assert.equal(normJid("1:2@s.whatsapp.net"), "1@s.whatsapp.net"));
