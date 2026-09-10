import { tmpdir } from "node:os";
import path from "node:path";

/** Fixed isolated-E2E paths shared by the config (server) and specs
 *  (runner): webServer.env does not propagate to spec workers. Files are
 *  rewritten on every run; the database never touches real data. */
export const E2E_DB = path.join(tmpdir(), "ci-e2e.db");
export const E2E_SEEDS = path.join(tmpdir(), "ci-e2e-seeds.json");
export const E2E_PORT = 4318;
/** The single installation container every seeded account belongs to:
 *  E2E models several accounts on ONE installation (item 18). */
export const E2E_CONTAINER = "e2e-installation";
