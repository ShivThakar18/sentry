/**
 * vite.config.ts: the dev server, plus a proxy to the core.
 *
 * The browser only ever talks to Vite (same origin, so no CORS). Vite forwards
 * /api/* to the core. Which core? CORE_URL decides:
 *
 *   npm run dev                                   → the mock core on :8001
 *   CORE_URL=http://localhost:8000 npm run dev    → the real core (on the Pi)
 *
 * The UI code never changes between the two. That's the whole point of 6d.
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const core = process.env.CORE_URL ?? "http://localhost:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on the network too, so the Pi's Chromium / your PC can open it
    proxy: {
      // The WebSocket. `ws: true` tells Vite to forward the HTTP "Upgrade"
      // handshake too; without it the browser's WebSocket fails to connect.
      "/api/ws": { target: core.replace(/^http/, "ws"), ws: true },
      // Everything else under /api is plain HTTP.
      "/api": { target: core, changeOrigin: true },
    },
  },
});
