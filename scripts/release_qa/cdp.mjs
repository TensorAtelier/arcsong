// A minimal DevTools-protocol driver: one new tab in the Chrome at $CDP (scripts/release-qa starts
// a private headless one), closed at the end. CDP is required, so it never drives a browser by accident.
import { writeFileSync } from "node:fs";
const base = process.env.CDP;
if (!base) throw new Error("set CDP to a DevTools URL, e.g. via scripts/release-qa");
const target = await (await fetch(`${base}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
export const consoleErrors = [];
ws.addEventListener("message", (e) => {
  const msg = JSON.parse(e.data);
  if (msg.method === "Runtime.exceptionThrown") consoleErrors.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
  if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(" "));
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
export const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const n = ++id;
    pending.set(n, (m) => (m.error ? reject(new Error(`${method}: ${m.error.message}`)) : resolve(m.result)));
    ws.send(JSON.stringify({ id: n, method, params }));
  });
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? "eval failed");
  return r.result.value;
};
export const shot = async (path) => {
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(path, Buffer.from(data, "base64"));
};
/** Click the centre of the first element matching `selector` with a real mouse event. */
export const click = async (selector) => {
  const box = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null; el.scrollIntoView({block: "center"}); const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!box) throw new Error(`no element ${selector}`);
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
};
export const key = async (k, code, text) => {
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, text, windowsVirtualKeyCode: text ? text.toUpperCase().charCodeAt(0) : 32 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, windowsVirtualKeyCode: text ? text.toUpperCase().charCodeAt(0) : 32 });
};
export const go = async (url) => { await send("Page.navigate", { url }); await sleep(1500); };
export const close = async () => { ws.close(); await fetch(`${base}/json/close/${target.id}`); };
await send("Page.enable");
await send("Runtime.enable");
await fetch(`${base}/json/activate/${target.id}`);
await send("Page.bringToFront");
