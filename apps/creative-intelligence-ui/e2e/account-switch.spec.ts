import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

// A07: switching accounts mid-request must not leak the previous
// account's private UI state. The ask is held open, the switch is
// held open to deterministically observe the switching gate, then
// both resolve and the late answer must never render.
//
// ORDERING: this file must sort before auth.spec.ts — that spec's
// "log out all sessions" journey destroys the seeded session tokens
// this spec plants. (Single worker, alphabetical file order.)
test.describe("account switch isolation", () => {
  test("late analyst answer from account A never renders under account B", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.employee, "/analyst");
    await expect(page.getByLabel("Ask Foap Analyst")).toBeVisible();
    await expect(page.getByText("Ada L").first()).toBeVisible();

    let releaseAsk!: () => void;
    const askHeld = new Promise<void>((resolve) => {
      releaseAsk = resolve;
    });
    await page.route("**/api/analyst/ask", async (route) => {
      await askHeld;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          conversation_id: "conv-emp-a",
          answer: {
            text: "STALE-ANSWER-FROM-EMP-A",
            language: "en",
            tables: [],
            findings_stored: [],
            follow_ups: [],
            warnings: [],
          },
          scope_snapshot: {},
          dataset_version: null,
        }),
      });
    });

    let releaseSwitch!: () => void;
    const switchHeld = new Promise<void>((resolve) => {
      releaseSwitch = resolve;
    });
    await page.route("**/api/auth/switch", async (route) => {
      await switchHeld;
      await route.continue();
    });

    // NOTE: the floating #account-menu overlaps the composer's Ask
    // button at this viewport (pre-existing layout), so submit with
    // the keyboard — same form-submit path as clicking Ask.
    await page.getByLabel("Ask Foap Analyst").fill("hook rate for each creative");
    const askSeen = page.waitForRequest("**/api/analyst/ask");
    await page.getByLabel("Ask Foap Analyst").press("Enter");
    // The ask request is now in flight (held above).
    await askSeen;

    await page.getByRole("button", { name: /Switch to Boss Admin/ }).click();
    // The switch POST is held: the dedicated switching state must
    // hide all protected content from either account.
    await expect(page.getByText("Switching accounts…")).toBeVisible();

    releaseSwitch();
    await expect(page.getByText("Boss Admin").first()).toBeVisible();
    await expect(page.getByLabel("Ask Foap Analyst")).toBeVisible();

    // Account A's answer resolves late, under B's identity.
    releaseAsk();
    await page.waitForTimeout(500);
    await expect(page.getByText("STALE-ANSWER-FROM-EMP-A")).toHaveCount(0);
    await expect(page.getByText("hook rate for each creative")).toHaveCount(0);
  });
});
