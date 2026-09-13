import { expect, test, type Page } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Full-demo visual acceptance: runs ONLY under FULL_DEMO=1, when the
 *  webServer seeds EXACTLY the ten synthetic campaigns, ten annotated
 *  creatives and their artwork (the small functional fixture is
 *  skipped here, so captures never show it). Populates every
 *  reference screen with representative content and captures it:
 *  dashboard, campaign/creative comparisons, saved findings,
 *  generated reports, workbook preview, analyst results, and the
 *  remaining routes (campaigns, benchmarks, analyst, admin, profile,
 *  settings) for fourteen-screen populated coverage.
 *
 *  Run: FULL_DEMO=1 npx playwright test e2e/02-full-demo.spec.ts
 */
const FULL = process.env.FULL_DEMO === "1";
const SHOTS = "test-results/screens";

/** Fail if the small functional fixture leaked into the visual set:
 *  the full-demo dataset is exactly the ten synthetic examples. */
async function expectCleanDemo(page: Page) {
  await expect(page.getByText("Seeded", { exact: true })).toHaveCount(0);
}

/** Every async area finished: no loading skeleton may remain, and no
 *  button may be stuck in its loading state, when the capture is taken.
 *  (Status spinners elsewhere — e.g. background report jobs — are
 *  legitimate settled content, so only button spinners count.
 *  LoadingButton keeps both faces mounted for width stability with the
 *  idle face visibility:hidden, so only a VISIBLE spinner is evidence
 *  of a stuck request.) */
async function expectReady(page: Page) {
  await expect(page.locator(".skel")).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator("button .spinner:visible")).toHaveCount(0, { timeout: 30000 });
}

/** No async button is stuck mid-request. LoadingButton marks the live
 *  state with aria-busy, which — unlike button text — ignores the
 *  hidden width-reservation face. */
async function expectNoBusyButton(page: Page) {
  await expect(page.locator('button[aria-busy="true"]')).toHaveCount(0, { timeout: 30000 });
}

/** Every rendered <img> under the selector decoded to real pixels
 *  (complete with a nonzero natural size) — a visible-but-broken
 *  image must never pass as settled content. */
async function expectImagesDecoded(page: Page, selector = "img") {
  await expect.poll(async () => {
    const states: boolean[] = await page.locator(selector).evaluateAll((els) =>
      els.map((el) => {
        const img = el as HTMLImageElement;
        return img.complete && img.naturalWidth > 0;
      }));
    return states.length > 0 && states.every(Boolean);
  }, { timeout: 30000 }).toBe(true);
}

test.describe("full demo visuals", () => {
  test.skip(!FULL, "needs a FULL_DEMO=1 seeded server");
  test.use({ viewport: { width: 1440, height: 1000 } });

  test("dashboard shows demo campaigns over scope averages", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/");
    // Top-5 table: the heaviest demo campaigns lead on real seeded rows.
    // (Scoped to table cells: the filter selects carry the same names as
    // hidden options earlier in the DOM.)
    await expect(page.locator("td", { hasText: "Spring Skincare Launch" }).first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator("td", { hasText: "Built For Real Life" }).first()).toBeVisible();
    // The benchmark legend names the comparison honestly (the select
    // option with the same text is hidden by the closed dropdown).
    await expect(page.locator(".legend", { hasText: "Scope Average" })).toBeVisible();
    // The default reporting period demonstrates real comparisons:
    // KPI percentage-change indicators render on open.
    await expect(page.locator(".kpi-card .kpi-trend").first()).toBeVisible({ timeout: 30000 });
    // Recommendation headings agree with their numbers: over the
    // trailing-30-day default scope Meta leads TikTok on ROAS at 1dp,
    // so the rail crowns Meta instead of declaring a tie.
    await expect(page.getByText("Meta Leads On ROAS")).toBeVisible();
    await expect(page.getByText("Tie on ROAS")).toHaveCount(0);
    // Charts populated, thumbnails decoded: the capture is settled.
    await expect(page.getByRole("img", { name: "Trend chart" })).toBeVisible({ timeout: 30000 });
    await expect(page.getByRole("img", { name: "Comparison bar chart" })).toBeVisible({ timeout: 30000 });
    await expectImagesDecoded(page, 'img[src*="/thumbnail"]');
    await expectCleanDemo(page);
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-dashboard.png`, fullPage: true, animations: "disabled" });
  });

  test("creatives grid shows seeded artwork", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/creatives");
    await expect(page.getByText("Glowing Skin Made Easy").first()).toBeVisible({ timeout: 30000 });
    const thumbs = page.locator('img[src*="/thumbnail"]');
    await expect(thumbs.first()).toBeVisible();
    // Exactly the ten demo creatives: five top cards plus ten table
    // rows, each with seeded artwork.
    await expect(page.getByText("All Creatives (10)")).toBeVisible({ timeout: 30000 });
    await expect(page.locator("table.tbl tbody tr")).toHaveCount(10, { timeout: 30000 });
    await expect(thumbs).toHaveCount(15, { timeout: 30000 });
    await expectImagesDecoded(page, 'img[src*="/thumbnail"]');
    await expectCleanDemo(page);
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-creatives.png`, fullPage: true, animations: "disabled" });
  });

  test("compare completes a four-way campaign comparison", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/compare");
    // The page auto-runs the top 4 campaigns by spend on load. The
    // acceptance capture is that completed four-way state: all four
    // cards plus every result section fully loaded.
    await expect(page.getByRole("button", { name: /^Remove / })).toHaveCount(4, { timeout: 60000 });
    // (Scoped to result cards: the picker selects carry the same names
    // as hidden options earlier in the DOM.)
    await expect(page.locator(".cmp-card h4", { hasText: "Spring Skincare Launch" })).toBeVisible();
    await expectNoBusyButton(page);
    await expect(page.getByText("Select two to four campaigns or creatives, then Apply Comparison.")).toHaveCount(0);
    await expect(page.getByText("No Daily Data For The Selected Campaigns.")).toHaveCount(0);
    await expect(page.getByRole("img", { name: /comparison chart/ }).first()).toBeVisible({ timeout: 60000 });
    for (const heading of ["Performance Over Time", "KPI Comparison", "Difference Summary",
      "Creative Attributes Comparison", "Key Takeaways", "Recommended Next Tests"]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expectImagesDecoded(page, 'img[src*="/thumbnail"]');
    await expectCleanDemo(page);
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-compare.png`, fullPage: true, animations: "disabled" });
    // Exercise the picker flow too: drop one campaign and re-apply.
    // Completion is proven by the comparison response itself — layout
    // absence alone can catch a mid-transition frame with stale cards.
    await page.getByRole("button", { name: "Remove Adventure Awaits" }).click();
    const compared = page.waitForResponse(
      (r) => r.request().method() === "GET" && r.url().includes("/api/compare/campaigns"),
      { timeout: 60000 },
    );
    await page.getByRole("button", { name: "Apply Comparison" }).click();
    await compared;
    await expectNoBusyButton(page);
    await expect(page.getByText("No Daily Data For The Selected Campaigns.")).toHaveCount(0);
    // Displayed selections match the requested three-way comparison.
    await expect(page.getByRole("button", { name: /^Remove / })).toHaveCount(3);
    await expect(page.getByRole("button", { name: "Remove Adventure Awaits" })).toHaveCount(0);
    await expect(page.getByRole("img", { name: /comparison chart/ }).first()).toBeVisible({ timeout: 60000 });
    await expectReady(page);
  });

  test("insights saves and lists a finding on demo data", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/insights");
    await page.getByRole("button", { name: "Save Insight" }).click();
    await expect(page.getByText(/Saved Insight —/)).toBeVisible({ timeout: 30000 });
    await expectReady(page);
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
    await expectReady(page);
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
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-ask.png`, fullPage: true, animations: "disabled" });
  });

  test("workbook preview renders", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/workbook");
    await expect(page.getByRole("heading").first()).toBeVisible({ timeout: 30000 });
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-workbook.png`, fullPage: true, animations: "disabled" });
  });

  test("remaining reference screens render on populated data", async ({ page, context }) => {
    // Completes fourteen-screen populated coverage: every route below
    // renders its heading with real demo content and no overflow.
    const seeds = readSeeds();
    const routes: Array<[shot: string, path: string, heading: string]> = [
      ["d-campaigns", "/campaigns", "Campaigns"],
      ["d-benchmarks", "/benchmarks", "Benchmarks Library"],
      ["d-analyst", "/analyst", "Your Creative Partner"],
      ["d-admin", "/admin", "Admin"],
      ["d-profile", "/profile", "Profile"],
      ["d-settings", "/settings", "Settings"],
    ];
    for (const [shot, path, heading] of routes) {
      await loginAs(context, page, seeds.admin, path);
      await expect(page.getByRole("heading", { level: 1, name: heading, exact: true }))
        .toBeVisible({ timeout: 30000 });
      await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      await expectReady(page);
      await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true, animations: "disabled" });
    }
  });

  test("mobile campaign filters stay readable", async ({ page, context }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/campaigns");
    await expect(page.getByLabel("Campaign Status", { exact: true })).toBeVisible({ timeout: 30000 });
    // Full ten-campaign table, lightest demo campaign included.
    await expect(page.getByText("Discover Something New").first()).toBeVisible();
    await expectCleanDemo(page);
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
    await expectReady(page);
    await page.screenshot({ path: `${SHOTS}/d-campaigns-mobile.png`, fullPage: true, animations: "disabled" });
  });
});
