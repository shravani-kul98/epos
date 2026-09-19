import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Port 5173 matches the origin already allowed by the backend CORS policy in api/main.py.
const DEV_PORT = 5173;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Charting is heavy and is not needed to render the first screen, so it is cached apart
        // from the framework and from application code that changes on most commits.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    // 0.0.0.0 so the dev server is reachable through a container port mapping.
    host: "0.0.0.0",
    port: DEV_PORT,
    strictPort: true,
  },
  preview: {
    host: "0.0.0.0",
    port: DEV_PORT,
    strictPort: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    outputFile: {
      junit: "test-results/junit/vitest.xml",
      html: "test-results/html/index.html",
    },
  },
});
