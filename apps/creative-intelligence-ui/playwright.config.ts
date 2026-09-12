import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import path from "node:path";
import { E2E_CONTAINER, E2E_DB, E2E_PORT, E2E_SEEDS } from "./e2e/paths";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${E2E_PORT}`,
    viewport: { width: 1280, height: 800 },
  },
  webServer: [
    {
      // Seed an isolated database, then serve the production React build
      // (dist/) plus API from the real FastAPI backend on one origin.
      // NOTE: cwd is the repo root (see below).
      command:
        `rm -f "${E2E_DB}" "${E2E_SEEDS}" && ` +
        `python3 apps/creative-intelligence-ui/e2e/seed.py "${E2E_DB}" "${E2E_SEEDS}" "${E2E_CONTAINER}" && ` +
        `python3 Backend/ci_backend/main.py --db "${E2E_DB}" --port ${E2E_PORT}`,
      url: `http://127.0.0.1:${E2E_PORT}/api/health`,
      reuseExistingServer: false,
      cwd: "../..",
      timeout: 120000,
      env: {
        ...(process.env as Record<string, string>),
        PYTHONDONTWRITEBYTECODE: "1",
        // Isolated media store for seeded demo artwork (empty on
        // small-fixture runs; populated under FULL_DEMO=1).
        CREATIVE_INTEL_MEDIA_DIR: path.join(tmpdir(), "ci-e2e-media"),
      },
    },
  ],
});
