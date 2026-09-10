import { readFileSync } from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { E2E_CONTAINER, E2E_SEEDS } from "./paths";

export interface Seeds {
  admin: string;
  employee: string;
  pending: string;
}

export function readSeeds(): Seeds {
  return JSON.parse(readFileSync(E2E_SEEDS, "utf-8")) as Seeds;
}

/** Plant a real server-issued session cookie (seeded DB), then load the app.
 *  The OAuth ceremony itself needs live WorkOS credentials (item 7) and is
 *  covered by backend stub tests; these journeys prove the gated app. */
export async function loginAs(
  context: BrowserContext,
  page: Page,
  token: string,
  path = "/",
  plantContainer = true,
): Promise<void> {
  // Plant this installation's container id before boot so the app's
  // adopt-on-boot bind is an idempotent no-op (item 18). Skipped to
  // model a foreign installation with its own fresh container.
  if (plantContainer) {
    await context.addInitScript(
      (container: string) => {
        try {
          window.localStorage.setItem("ci-container-id", container);
        } catch {
          /* ignore */
        }
      },
      E2E_CONTAINER,
    );
  }
  await context.addCookies([
    { name: "ci_session", value: token, domain: "127.0.0.1", path: "/" },
  ]);
  await page.goto(path);
}
