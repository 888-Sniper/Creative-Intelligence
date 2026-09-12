import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Full-demo visual acceptance: runs ONLY under FULL_DEMO=1, when the
 *  webServer seeds the ten synthetic campaigns, ten annotated
 *  creatives and their artwork on top of the small functional
 *  fixture (which the rest of the suite keeps). Populates every
 *  reference screen with representative content and captures it:
 *  dashboard, campaign/creative comparisons, saved findings,
 *  generated reports, workbook preview and analyst results.
 *
 *  Run: FULL_DEMO=1 npx playwright test e2e/02-full-demo.spec.ts
 */
const FULL = process.env.FULL_DEMO === "1";
const SHOTS = "test-results/screens";

test.describe("full demo visuals", () => {
  test.skip(!FULL, "needs a FULL_DEMO=1 seeded server");
  test.use({ viewport: { width: 1440, height: 1000 } });

  test("dashboard shows demo campaigns over scope averages", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/");
    // Top-5 table: the heaviest demo campaigns lead on real seeded rows.
    await expect(page.getByText("Spring Skincare Launch").first()).toBeVisible({ timeout: 30000 });
    await expect(page.getByText("Built For Real Life").first()).toBeVisible();
    // The benchmark legend names the comparison honestly (the select
    // option with the same text is hidden by the closed dropdown).
    await expect(page.locator(".legend", { hasText: "Scope Average" })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/d-dashboard.png`, fullPage: true, animations: "disabled" });
  });

  test("creatives grid shows seeded artwork", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/creatives");
    await expect(page.getByText("Glowing Skin Made Easy").first()).toBeVisible({ timeout: 30000 });
    const thumbs = page.locator('img[src*="/thumbnail"]');
    await expect(thumbs.first()).toBeVisible();
    expect(await thumbs.count()).toBeGreaterThanOrEqual(10);
    await page.screenshot({ path: `${SHOTS}/d-creatives.png`, fullPage: true, animations: "disabled" });
  });

  test("compare completes a multi-campaign comparison", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/compare");
    // The page auto-runs the top 4 campaigns by spend on load, so the
    // multi-campaign layout is already complete under the full demo;
    // the heaviest demo campaigns lead it.
    await expect(page.getByRole("img", { name: /comparison chart/ }).first()).toBeVisible({ timeout: 60000 });
    await expect(page.getByText("Spring Skincare Launch").first()).toBeVisible();
    // Exercise the picker flow too: drop one campaign and re-apply,
    // keeping a completed (three-way) comparison on screen.
    await page.getByRole("button", { name: "Remove Adventure Awaits" }).click();
    await page.getByRole("button", { name: "Apply Comparison" }).click();
    await expect(page.getByText("Select two to four campaigns or creatives, then Apply Comparison.")).toHaveCount(0);
    await expect(page.getByRole("img", { name: /comparison chart/ }).first()).toBeVisible({ timeout: 60000 });
    await page.screenshot({ path: `${SHOTS}/d-compare.png`, fullPage: true, animations: "disabled" });
  });

  test("insights saves and lists a finding on demo data", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/insights");
    await page.getByRole("button", { name: "Save Insight" }).click();
    await expect(page.getByText(/Saved Insight —/)).toBeVisible({ timeout: 30000 });
    await page.screenshot({ path: `${SHOTS}/d-insights.png`, fullPage: true, animations: "disabled" });
  });

  // NOTE: reports runs BEFORE ask on purpose. A grounded answer
  // leaves QA reviews pending, and the review-to-zero gate then
  // (correctly) blocks the one-pager export until they are reviewed.
  test("reports generates a downloadable report", async ({ page, context }) => {
    test.setTimeout(120000);
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/reports");
    await page.getByRole("button", { name: "Generate Report" }).click();
    await expect(page.getByRole("link", { name: /Download / }).first()).toBeVisible({ timeout: 90000 });
    await page.screenshot({ path: `${SHOTS}/d-reports.png`, fullPage: true, animations: "disabled" });
  });

  test("ask answers at platform level with honest ties", async ({ page, context }) => {
    test.setTimeout(120000);
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/ask");
    await page.getByLabel("Ask a question about your marketing data").fill("Which platform has the best ROAS?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Suggested Follow-Ups")).toBeVisible({ timeout: 60000 });
    // Platform-level answer: names Meta/TikTok, never a creative title.
    await expect(page.getByText(/Meta|TikTok/).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/d-ask.png`, fullPage: true, animations: "disabled" });
  });

  test("workbook preview renders", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/workbook");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 30000 });
    await page.screenshot({ path: `${SHOTS}/d-workbook.png`, fullPage: true, animations: "disabled" });
  });

  test("mobile campaign filters stay readable", async ({ page, context }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/campaigns");
    await expect(page.getByLabel("Campaign Status")).toBeVisible({ timeout: 30000 });
    // Full ten-campaign table, lightest demo campaign included.
    await expect(page.getByText("Discover Something New").first()).toBeVisible();
    // No control may be squeezed to an unreadable sliver: every
    // filter field keeps a usable minimum width and fields in the
    // same row never overlap.
    const boxes = await page.locator(".filter-grid .field").evaluateAll((els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, w: r.width, h: r.height };
      }),
    );
    expect(boxes.length).toBeGreaterThan(0);
    for (const b of boxes) expect(b.w).toBeGreaterThanOrEqual(120);
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const b = boxes[j];
        const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        expect(overlapX <= 1 || overlapY <= 1).toBe(true);
      }
    }
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `${SHOTS}/d-campaigns-mobile.png`, fullPage: true, animations: "disabled" });
  });
});
