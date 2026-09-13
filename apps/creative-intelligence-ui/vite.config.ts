import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend. Production builds are
// served by the backend itself (see Backend/ci_backend/routers/product.py),
// so no CORS configuration is needed in either mode.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:4318",
      // Brand files are served by the backend (single source in
      // Web/assets); proxy them in dev so the logo works on :5174 too.
      "/foap-logo.png": "http://127.0.0.1:4318",
      "/favicon.png": "http://127.0.0.1:4318",
    },
  },
});
