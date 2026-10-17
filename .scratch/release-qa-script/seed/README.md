Seed for `release-qa-script` (cycle 2): the scripts cycle 1's release QA ran from the PM scratchpad.

- `cdp.mjs` — a tiny DevTools-protocol driver (one new tab, closed at the end); `CDP=http://127.0.0.1:9333`.
- `release-qa.mjs` — journeys 1–5 from `docs/product/product.md` → Release against its own fake-Engine
  server on port 8851 and a temp data dir: `CDP=… node release-qa.mjs <repo>`.
- `shots.mjs` — the README screenshots (dark, 1440 px at 1.5×) from the running app on 8840.
- Browser: a private headless Chrome, e.g. `Google Chrome --headless=new --remote-debugging-port=9333
  --user-data-dir=<tmp> --autoplay-policy=no-user-gesture-required` (autoplay lets playback be tested).
- `cycle-1-result.log` — the passing run on the v0.2.0 build.
