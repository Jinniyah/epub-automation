/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Flask/waitress's dev-time port. launcher.py assigns a free port
// dynamically in production; for local frontend dev against a real
// backend, run the backend with FLASK_DEV_PORT set to match, or update
// this constant. See frontend/README.md for the full rationale.
const BACKEND_DEV_PORT = 5000;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${BACKEND_DEV_PORT}`,
        changeOrigin: true,
        configure: (proxy) => {
          // Rewrite Origin to the proxy target so Flask's Origin-vs-host
          // check (backend/app.py::_origin_is_allowed()) sees a
          // same-origin request, matching production traffic. Do not
          // relax that backend check instead -- see frontend/README.md.
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("origin", `http://127.0.0.1:${BACKEND_DEV_PORT}`);
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      reportsDirectory: "./coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/test/**",
        "src/**/*.test.{ts,tsx}",
      ],
      thresholds: {
        lines: 80,
        statements: 80,
        functions: 80,
        branches: 80,
      },
    },
  },
});
