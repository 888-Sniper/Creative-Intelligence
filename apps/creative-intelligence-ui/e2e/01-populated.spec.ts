import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Populated-state captures: the 14-screen suite proves composition on
 *  empty starting states; these journeys drive Compare, Saved Insights
 *  and Ask The Data into their populated states and capture those.
 *
 *  ORDERING: sorts after 00-screens (admin session still live) and
 *  before auth.spec.ts (which destroys it). "Save Insight" persists one
 *  view row; no other spec asserts on views, conversations or periods.
 */
const SHOTS = "test-results/screens";

test.describe("populated states", () => {
  test.use({ viewport: { width: 1440, height: 1000 } });

  test("compare runs a period comparison", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/compare");
    await page.getByLabel("A From").fill("2023-12-25");
    await page.getByLabel("A To").fill("2023-12-31");
    await page.getByLabel("B From").fill("2024-01-01");
    await page.getByLabel("B To").fill("2024-01-07");
    await page.getByRole("button", { name: "Compare Periods" }).click();
    await expect(page.getByRole("columnheader", { name: "B−A" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `${SHOTS}/p-compare.png`, fullPage: true, animations: "disabled" });
  });

  test("insights saves and lists an insight", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/insights");
    await page.getByRole("button", { name: "Save Insight" }).click();
    await expect(page.getByText(/Saved Insight —/)).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `${SHOTS}/p-insights.png`, fullPage: true, animations: "disabled" });
  });

  test("ask answers a question", async ({ page, context }) => {
    test.setTimeout(120000);
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/ask");
    await page.getByLabel("Ask a question about your marketing data").fill("Which platform has the best ROAS?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Suggested Follow-Ups")).toBeVisible({ timeout: 60000 });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `${SHOTS}/p-ask.png`, fullPage: true, animations: "disabled" });
  });
});
