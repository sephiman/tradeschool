/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    /**
     * Vitest defaults to 5s, which is the wrong order of magnitude for this suite: several files
     * build the whole 220-page book or annotate all 36 lessons, and a single one of those takes
     * seconds on an idle machine and longer when the run is parallel. At 5s they passed alone and
     * failed together — flaky by construction rather than by any defect. The genuinely long ones
     * (typesetting the book, generating the link report) still declare their own timeout.
     */
    testTimeout: 30_000,
  },
});
