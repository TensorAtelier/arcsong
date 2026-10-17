// Release QA: journeys 1–5 from docs/product/product.md on a fresh fake-Engine server.
// CDP=http://127.0.0.1:9333 node release-qa.mjs <repo>
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { click, close, consoleErrors, evaluate, go, key, send, shot, sleep } from "./cdp.mjs";

const REPO = process.argv[2];
const PORT = 8851;
const BASE = `http://127.0.0.1:${PORT}/`;
const DATA = mkdtempSync(join(tmpdir(), "arcsong-qa-"));
const results = [];
let server;

function startServer() {
  server = spawn("uv", ["run", "arcsong", "serve", "--engine", "fake", "--port", String(PORT), "--data", DATA], { cwd: REPO, stdio: "ignore" });
}
async function stopServer() {
  server.kill("SIGTERM");
  await new Promise((r) => server.once("exit", r));
}
async function waitFor(expr, ms = 30000, what = expr) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try { if (await evaluate(expr)) return; } catch {}
    await sleep(300);
  }
  throw new Error(`timed out waiting for ${what}`);
}
const up = async () => { for (let i = 0; i < 60; i++) { try { await fetch(BASE + "api/jobs"); return; } catch { await sleep(500); } } throw new Error("server did not start"); };
const clickText = (selector, text) => evaluate(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim().startsWith(${JSON.stringify(text)})); if (!el) return false; el.click(); return true; })()`);
const fill = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
const overflow = () => evaluate(`document.documentElement.scrollWidth > document.documentElement.clientWidth + 1`);
const desktop = () => send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
const phone = () => send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });

async function journey(name, fn) {
  const before = consoleErrors.length;
  try {
    const evidence = await fn();
    const errors = consoleErrors.slice(before);
    results.push({ name, pass: errors.length === 0, evidence, errors });
  } catch (e) {
    await shot(`qa-fail-${name.split(" ")[0]}`).catch(() => {});
    results.push({ name, pass: false, evidence: String(e.message ?? e), errors: consoleErrors.slice(before) });
  }
  console.log(JSON.stringify(results.at(-1)));
}

const STYLE = "English, late-night lo-fi soul, warm Rhodes, brushed drums, soft male vocal";
const LYRICS = "[Verse]\nRain against the window of the corner room\n\n[Chorus]\nStay a little longer, let the record play";

try {
  startServer();
  await up();
  await desktop();

  await journey("J1 first song [core]", async () => {
    await go(BASE);
    await waitFor(`location.hash === "#/setup"`, 10000, "opening on Setup");
    // Edge: Create refuses to render before the weights exist.
    await go(BASE + "#/");
    await sleep(800);
    const gated = await evaluate(`document.querySelector('.cta button[type=submit]').disabled && !!document.querySelector('.notice')`);
    await go(BASE + "#/setup");
    await waitFor(`!!document.querySelector('.setup')`);
    await clickText("button", "I acknowledge the model licence");
    await waitFor(`[...document.querySelectorAll('button')].some(b => b.textContent.startsWith('Download (') && !b.disabled)`);
    await clickText("button", "Download (");
    await waitFor(`document.body.textContent.includes('Setup is complete')`, 30000, "setup complete");
    await go(BASE + "#/");
    await sleep(800);
    await clickText(".mode", "Single song");
    await fill("#style", STYLE);
    await fill("#lyrics", LYRICS);
    await sleep(300);
    await click(".cta button[type=submit]");
    await waitFor(`!!document.querySelector('.finished li')`, 60000, "a finished song");
    const title = await evaluate(`document.querySelector('.finished .row-title').textContent`);
    await click(".finished button.play");
    await sleep(2500);
    const playing = await evaluate(`!!document.querySelector('.now-playing') && document.querySelector('.now-playing .clock').textContent`);
    await click(".now-playing button.play");
    await stopServer();
    startServer();
    await up();
    await go(BASE + "#/library");
    await waitFor(`!!document.querySelector('.song-row')`, 15000, "the song after a restart");
    const kept = await evaluate(`document.querySelector('.song-row .song-title').textContent`);
    if (!gated) throw new Error("Create was not gated before Setup");
    if (kept !== title) throw new Error(`after restart: ${kept} vs ${title}`);
    return { gatedBeforeSetup: gated, title, barClock: playing, keptAfterRestart: kept };
  });

  await journey("J2 sketch and pick [core]", async () => {
    await go(BASE + "#/");
    await sleep(800);
    await fill("#style", STYLE);
    await fill("#lyrics", LYRICS);
    await sleep(300);
    await click(".cta button[type=submit]"); // Sketch · 4 takes is the default
    await waitFor(`/Compare your last sketch \\(4 takes\\)/.test(document.querySelector('.compare-link')?.textContent ?? '')`, 120000, "the finished sketch's Compare link");
    const linkText = await evaluate(`document.querySelector('.compare-link').textContent`);
    await click(".compare-link");
    await waitFor(`document.querySelectorAll('.take audio').length === 4`, 15000, "4 takes in Compare");
    await sleep(1500);
    const audios = `[...document.querySelectorAll('.take audio')].map(a => !a.paused)`;
    await key("1", "Digit1", "1"); await sleep(2000);
    const one = await evaluate(audios);
    const t1 = await evaluate(`document.querySelectorAll('.take audio')[0].currentTime`);
    await key("2", "Digit2", "2"); await sleep(600);
    const two = await evaluate(audios);
    const t2 = await evaluate(`document.querySelectorAll('.take audio')[1].currentTime`);
    await key(" ", "Space", " "); await sleep(500);
    const paused = await evaluate(audios);
    await key("s", "KeyS", "s"); await sleep(800);
    const starred = await evaluate(`document.querySelectorAll('.take')[1].querySelector('.star').getAttribute('aria-pressed')`);
    if (!one[0] || !two[1] || two[0] || paused.some(Boolean) || starred !== "true" || t2 < t1 - 0.5) throw new Error(JSON.stringify({ one, two, paused, starred, t1, t2 }));
    await clickText(".take button", "Finalize this take");
    await go(BASE + "#/library");
    await waitFor(`[...document.querySelectorAll('.project .take-name')].some(e => e.textContent.startsWith('Final'))`, 60000, "the Final in the sketch card");
    // Edge: phone width, no sideways scroll on Compare.
    await go(BASE + "#/compare/" + (await evaluate(`document.querySelector('.project a.button.primary').getAttribute('href').split('/').pop()`)));
    await phone(); await sleep(1200);
    const phoneOverflow = await overflow();
    await shot("qa-phone-compare");
    await desktop();
    return { finishedLink: linkText, key1: one, key2: two, sharedPlayhead: { t1: +t1.toFixed(2), t2: +t2.toFixed(2) }, spacePaused: !paused.some(Boolean), starred, final: true, phoneOverflow };
  });

  await journey("J3 library [core]", async () => {
    await go(BASE + "#/library");
    await waitFor(`!!document.querySelector('.project')`);
    await fill(".page-head input[type=search]", "zzz-no-such-song");
    await sleep(300);
    const empty = await evaluate(`document.querySelector('.empty')?.textContent ?? null`);
    await fill(".page-head input[type=search]", "");
    await clickText(".segmented button", "★ Starred");
    await sleep(300);
    const starredRows = await evaluate(`document.querySelectorAll('.take-row, .song-row').length`);
    await clickText(".segmented button", "All");
    await sleep(300);
    // Rename through the ⋯ menu of the single song.
    await click(".song-row .menu-anchor button");
    await waitFor(`!!document.querySelector('.menu')`, 3000, "the menu");
    await clickText(".menu button", "Rename");
    await sleep(200);
    await fill(".title-edit input", "Kettle Song, take one!");
    await evaluate(`document.querySelector('.title-edit input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))`);
    await waitFor(`document.querySelector('.song-row .song-title')?.textContent === 'Kettle Song, take one!'`, 5000, "the new title");
    await click(".song-row .menu-anchor button");
    await waitFor(`!!document.querySelector('.menu')`, 3000, "the menu");
    const href = await evaluate(`[...document.querySelectorAll('.menu a')].find(x => x.textContent === 'Download FLAC').getAttribute('href')`);
    await key("Escape", "Escape");
    await sleep(200);
    const res = await fetch(new URL(href, BASE));
    const disposition = res.headers.get("content-disposition");
    // Delete through the menu, with confirmation.
    await click(".song-row .menu-anchor button");
    await waitFor(`!!document.querySelector('.menu')`, 3000, "the menu");
    await clickText(".menu button", "Delete");
    await sleep(200);
    await clickText(".confirm button", "Delete permanently");
    await waitFor(`!document.querySelector('.song-row')`, 5000, "the song to go");
    if (!empty || !disposition?.includes("kettle-song-take-one")) throw new Error(JSON.stringify({ empty, disposition }));
    await phone(); await sleep(800);
    const phoneOverflow = await overflow();
    await desktop();
    return { emptySearch: empty, starredRows, renamed: true, download: disposition, deleted: true, phoneOverflow };
  });

  await journey("J4 score", async () => {
    await go(BASE + "#/");
    await sleep(800);
    await clickText(".tabs button", "Plan a melody");
    await fill("#style", STYLE);
    await fill("#lyrics", LYRICS);
    await sleep(300);
    await click(".cta button[type=submit]");
    await waitFor(`location.hash.startsWith('#/score/job/')`, 10000, "the Score page");
    await waitFor(`!!document.querySelector('.paper svg') && !!document.querySelector('.validity .ok')`, 30000, "notation and a valid check");
    const text = await evaluate(`document.querySelector('#abc').value`);
    await fill("#abc", text + "\n% edited");
    await waitFor(`document.querySelector('.badge.draft')?.textContent === 'edited'`, 5000, "the edited badge");
    await clickText(".render button", "Render the song");
    await waitFor(`location.hash === '#/' && !!document.querySelector('.running, .waiting li, .finished li')`, 10000, "the render queued");
    return { notation: true, valid: true, edited: true, rendered: true };
  });

  await journey("J5 cover", async () => {
    await go(BASE + "#/setup");
    await waitFor(`[...document.querySelectorAll('button')].filter(b => b.textContent.startsWith('Download (')).length > 0`, 10000);
    await clickText("button", "Download (");
    await waitFor(`document.querySelectorAll('.setup-section .ok-text, .setup-section .small.ok-text').length >= 2 || document.body.textContent.split('Ready').length > 2`, 30000, "covers ready");
    await go(BASE + "#/");
    await sleep(800);
    await clickText(".tabs button", "Cover a recording");
    await sleep(300);
    const { root } = await send("DOM.getDocument", { depth: -1 });
    const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: "#recording" });
    await send("DOM.setFileInputFiles", { nodeId, files: [process.cwd() + "/qa-tone.wav"] });
    await fill("#cover-style", "English, slow jazz trio, brushed drums, warm male vocal");
    await click(".check-label input");
    await sleep(300);
    await waitFor(`!document.querySelector('form[aria-label="Cover a recording"] button[type=submit]').disabled`, 15000, "Transcribe enabled");
    await click('form[aria-label="Cover a recording"] button[type=submit]');
    await waitFor(`location.hash.startsWith('#/score/job/') && !!document.querySelector('.paper svg')`, 60000, "the transcribed Score");
    return { uploaded: "qa-tone.wav", transcribedScore: true };
  });
} finally {
  await evaluate(`document.querySelectorAll('audio').forEach(a => a.pause())`).catch(() => {});
  await close();
  if (server) await stopServer().catch(() => {});
  rmSync(DATA, { recursive: true, force: true });
  console.log("SUMMARY", results.map((r) => `${r.pass ? "PASS" : "FAIL"} ${r.name}`).join(" | "));
}
