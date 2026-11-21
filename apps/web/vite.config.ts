import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
// @ts-expect-error — plain ESM build script without type declarations
import { gestureAssets } from "./scripts/gesture-assets.mjs";

const api = process.env.NEXORA_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), gestureAssets()],
  // The landmark worker is an ES module (it lazy-loads MediaPipe with import()).
  worker: { format: "es" },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": api, "/health": api },
  },
  preview: { host: "127.0.0.1", port: 4173, proxy: { "/api": api, "/health": api } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
