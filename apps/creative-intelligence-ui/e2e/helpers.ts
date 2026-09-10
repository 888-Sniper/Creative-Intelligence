import { readFileSync } from "node:fs";
import type { BrowserContext, Page } from "@playwright/test";
import { E2E_SEEDS } from "./paths";

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
export async function loginAs(context: BrowserContext, page: Page, token: string, path = "/"): Promise<void> {
  await context.addCookies([
    { name: "ci_session", value: token, domain: "127.0.0.1", path: "/" },
  ]);
  await page.goto(path);
}
