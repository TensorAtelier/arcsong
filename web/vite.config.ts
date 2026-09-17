import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Built assets go inside the Python package, so `songloom serve` needs no Node at runtime.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../songloom/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8840" } },
});
