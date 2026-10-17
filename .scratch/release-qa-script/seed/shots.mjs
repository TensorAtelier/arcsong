// README screenshots from the running app, in a private headless Chrome (CDP on :9333).
import { writeFileSync } from "node:fs";
import { click, close, evaluate, go, send, sleep } from "./cdp.mjs";
const OUT = process.argv[2];
const W = 1440;
const shoot = async (name, height) => {
  const h = height ?? (await evaluate(`Math.ceil(document.documentElement.scrollHeight)`));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: h, deviceScaleFactor: 1.5, mobile: false });
  await sleep(700);
  const { data } = await send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: W, height: h, scale: 1 } });
  writeFileSync(`${OUT}/${name}.png`, Buffer.from(data, "base64"));
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 900, deviceScaleFactor: 1.5, mobile: false });
  console.log(name, h);
};
// Type into a React-controlled field.
const fill = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
try {
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "dark" }] });
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: 900, deviceScaleFactor: 1.5, mobile: false });
  const base = "http://127.0.0.1:8840/";
  await go(base + "#/");
  await evaluate(`localStorage.setItem("arcsong.theme", "dark")`);
  await go(base + "#/");
  await sleep(1500);
  // Dismiss old failure cards in this profile (the app remembers dismissals per browser).
  for (let i = 0; i < 20; i++) {
    const left = await evaluate(`(() => { const b = [...document.querySelectorAll('.alert button')].find(x => x.textContent === 'Dismiss'); b?.click(); return !!b; })()`);
    if (!left) break;
    await sleep(200);
  }
  await go(base + "#/");
  await sleep(1500);
  console.log("failure cards after reload:", await evaluate(`document.querySelectorAll('.alert').length`));
  await fill("#style", "English, late-night lo-fi soul, warm Rhodes, brushed drums, soft male vocal");
  await fill("#lyrics", "[Verse]\nRain against the window of the corner room\nCoffee going cold beside the afternoon\n\n[Chorus]\nStay a little longer, let the record play\nNothing out there needs us till the break of day");
  await sleep(500);
  await shoot("create");

  await click("#tab-cover");
  await sleep(600);
  await shoot("cover");

  await go(base + "#/library");
  await sleep(2500);
  // The player bar on screen: start a song, pause it a moment in.
  await click(".song-row button.play");
  await sleep(4000);
  await evaluate(`document.querySelector('.now-playing button.play').click()`);
  await sleep(800);
  await shoot("library", 900);

  await go(base + "#/compare/13");
  await sleep(3000);
  await click(".take:nth-child(2) button.play");
  await sleep(6000);
  await shoot("compare", 900);
  await click(".take:nth-child(2) button.play");

  await go(base + "#/score/song/3");
  await sleep(3500);
  await shoot("score", 1180);

  await go(base + "#/setup");
  await sleep(2000);
  await shoot("setup");
} finally {
  await evaluate(`document.querySelectorAll('audio').forEach(a => a.pause())`).catch(() => {});
  await close();
}
