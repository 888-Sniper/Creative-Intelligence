import { expect, test, type Page } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Five-campaign presentation pack through the REAL import workflow.
 *  Runs ONLY under DEMO_PACK=1 with a fresh seeded server (the default
 *  suite keeps the small deterministic fixture untouched):
 *
 *    DEMO_PACK=1 npx playwright test e2e/03-demo-pack.spec.ts
 *
 *  An admin clicks "Add Demo Data Once" in /admin; every assertion
 *  below reads backend-driven screens — never the retired filler.
 */
const DEMO = process.env.DEMO_PACK === "1";
const SHOTS = "test-results/screens";

const FIVE = [
  "First Light Ritual",
  "One Sip Ahead",
  "Make Room For Better",
  "The 6AM Commitment",
  "Find Your Focus",
];

async function settle(page: Page) {
  // Anti-vacuous guard: prove the admin session reached the app shell.
  await expect(
    page.getByRole("link", { name: "Dashboard", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".skel")).toHaveCount(0, { timeout: 30000 });
  await expect(page.locator("button .spinner:visible")).toHaveCount(0, {
    timeout: 30000,
  });
  await page.evaluate(() => document.fonts.ready);
}

/** The Demo Data panel lives in the "Advanced · Demo Tools"
 *  disclosure on /admin: expand it before touching pack controls. */
async function openDemoTools(page: Page) {
  const details = page.locator("details.adv-disclosure").first();
  if ((await details.getAttribute("open")) === null) {
    await details.locator("summary").click();
    await expect(details).toHaveAttribute("open", "");
  }
}

test.describe("five-campaign demo pack", () => {
  test.skip(!DEMO, "needs DEMO_PACK=1 with a fresh seeded server");
  test.use({ viewport: { width: 1440, height: 1000 } });

  test("admin imports the pack once via Add Demo Data Once", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/admin");
    await settle(page);
    await openDemoTools(page);
    // Honest preview before anything is created.
    await expect(
      page.getByText(/Will Create: 5 Campaign\(s\), 15 Creative\(s\)/),
    ).toBeVisible({ timeout: 30000 });
    await page
      .getByRole("button", { name: "Add Demo Data Once" })
      .click();
    await expect(page.getByText("Sample Data Added.")).toBeVisible({
      timeout: 120000,
    });
    await expect(
      page.getByText(/Remaining: 5\/5 Campaign\(s\), 15\/15 Creative\(s\)/),
    ).toBeVisible();
    // The one-time button is gone after import: no casual re-import.
    await expect(
      page.getByRole("button", { name: "Add Demo Data Once" }),
    ).toHaveCount(0);
    await page.screenshot({
      path: `${SHOTS}/demo-admin.png`,
      fullPage: true,
      animations: "disabled",
    });
  });

  test("campaigns page shows all five sample campaigns", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/campaigns");
    await settle(page);
    for (const name of FIVE) {
      await expect(
        page.locator("td", { hasText: name }).first(),
      ).toBeVisible({ timeout: 30000 });
    }
    await page.screenshot({
      path: `${SHOTS}/demo-campaigns.png`,
      fullPage: true,
      animations: "disabled",
    });
  });

  test("all fifteen creatives are discoverable", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/creatives");
    await settle(page);
    // "Top Creatives" shows four cards; the full set lives in the
    // All Creatives grid view (15 sample creatives plus the 4 seeded
    // fixture rows on a fresh test server — the count label, the
    // cards and the titles must all agree).
    const allHeading = page.getByRole("heading", { name: /All Creatives/ });
    await expect(allHeading).toBeVisible({ timeout: 30000 });
    const total = Number(
      ((await allHeading.textContent()) ?? "").replace(/[^0-9]/g, ""),
    );
    expect(total).toBeGreaterThanOrEqual(15);
    await page.getByRole("button", { name: "Grid View" }).click();
    const all = page.locator(".panel", {
      has: page.getByRole("heading", { name: /All Creatives/ }),
    });
    await expect(all.locator(".creative-card")).toHaveCount(total, {
      timeout: 30000,
    });
    for (const title of [
      "The Mirror Test",
      "Morning In Three Steps",
      "Texture In Motion",
      "Before The First Meeting",
      "The Desk-Side Brew",
      "Thirty Seconds To Coffee",
      "The Drawer Reset",
      "One Shelf, Three Uses",
      "A Cleaner Start",
      "Alarm To Action",
      "The First Ten Minutes",
      "Your Pace, Your Start",
      "Desk Noise, Meet Silence",
      "Inside A Focus Session",
      "One Button, Clearer Work",
    ]) {
      await expect(all.getByText(title).first()).toBeVisible();
    }
    // Every card image decoded to real pixels.
    const bad = await all.locator(".creative-card img").evaluateAll((els) =>
      els.filter((el) => {
        const img = el as HTMLImageElement;
        return !(img.complete && img.naturalWidth > 0);
      }).length,
    );
    expect(bad).toBe(0);
    // Money facts reconcile: pooled ROAS is a real multiple on this
    // single-currency pack, never a coerced 0.0x.
    await expect(
      page.locator(".kpi-card", { hasText: "Average ROAS" }),
    ).not.toContainText("0.0x");
    // List view: expanding a creative shows working details.
    await page.getByRole("button", { name: "List View" }).click();
    await page
      .getByRole("button", { name: "The Mirror Test", exact: true })
      .click();
    await expect(page.locator("#creative-detail")).toBeVisible({
      timeout: 30000,
    });
    await page.screenshot({
      path: `${SHOTS}/demo-creatives.png`,
      fullPage: true,
      animations: "disabled",
    });
  });

  test("saved four-campaign comparison restores all four", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/insights");
    await settle(page);
    const card = page
      .locator(".cmp-card", {
        has: page.getByRole("heading", { name: "Four Contrasts" }),
      })
      .first();
    await expect(card).toBeVisible({ timeout: 30000 });
    await card.getByRole("button", { name: "Open Insight" }).click();
    await expect(page).toHaveURL(/mode=campaigns/);
    for (const name of [
      "First Light Ritual",
      "One Sip Ahead",
      "The 6AM Commitment",
      "Find Your Focus",
    ]) {
      await expect(page.getByText(name).first()).toBeVisible({
        timeout: 30000,
      });
    }
    await page.screenshot({
      path: `${SHOTS}/demo-compare.png`,
      fullPage: true,
      animations: "disabled",
    });
  });

  test("sample reports are listed with working downloads", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/reports");
    await settle(page);
    const link = page.getByRole("link", {
      name: "Download Sample Report - Pack Overview (Slides)",
    });
    await expect(link).toBeVisible({ timeout: 30000 });
    const dl = await Promise.all([
      page.waitForEvent("download"),
      link.click(),
    ]).then(([d]) => d);
    expect(dl.suggestedFilename()).toMatch(/\.pptx$/);
    const path = await dl.path();
    expect(path).toBeTruthy();
    await page.screenshot({
      path: `${SHOTS}/demo-reports.png`,
      fullPage: true,
      animations: "disabled",
    });
  });

  test("rename round-trips without losing cleanup provenance", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/admin");
    await settle(page);
    await openDemoTools(page);
    await page
      .getByLabel("Sample Campaign To Rename")
      .selectOption({ label: "One Sip Ahead" });
    await page.getByLabel("New Campaign Name").fill("One Sip Ahead Test");
    await page.getByRole("button", { name: "Rename", exact: true }).click();
    await expect(
      page.getByText("Sample Campaign Renamed. Cleanup Provenance Kept."),
    ).toBeVisible({ timeout: 30000 });
    // No hard reload: the renamed campaign resolves on Campaigns.
    await page.goto("/campaigns");
    await settle(page);
    await expect(
      page.locator("td", { hasText: "One Sip Ahead Test" }).first(),
    ).toBeVisible({ timeout: 30000 });
    // Rename it back so later journeys see the catalogue names.
    await page.goto("/admin");
    await settle(page);
    await openDemoTools(page);
    await page
      .getByLabel("Sample Campaign To Rename")
      .selectOption({ label: "One Sip Ahead Test" });
    await page.getByLabel("New Campaign Name").fill("One Sip Ahead");
    await page.getByRole("button", { name: "Rename", exact: true }).click();
    await expect(
      page.getByText("Sample Campaign Renamed. Cleanup Provenance Kept."),
    ).toBeVisible({ timeout: 30000 });
  });

  test("delete journey: five become four and stay four", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/admin");
    await settle(page);
    await openDemoTools(page);
    const row = page.locator("li", { hasText: "Find Your Focus" }).last();
    await row.getByRole("button", { name: "Delete…" }).click();
    await expect(
      page.getByText(/Removes “Find Your Focus”:/),
    ).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "Confirm Delete" }).click();
    await expect(
      page.getByText("Sample Campaign Deleted. It Will Not Return."),
    ).toBeVisible({ timeout: 60000 });
    // No hard reload: Campaigns shows four with recalculated totals.
    await page.goto("/campaigns");
    await settle(page);
    await expect(
      page.locator("td", { hasText: "Find Your Focus" }),
    ).toHaveCount(0, { timeout: 30000 });
    for (const name of FIVE.slice(0, 4)) {
      await expect(
        page.locator("td", { hasText: name }).first(),
      ).toBeVisible();
    }
    // Refresh/reopen: the deleted campaign stays deleted.
    await page.reload();
    await settle(page);
    await expect(
      page.locator("td", { hasText: "Find Your Focus" }),
    ).toHaveCount(0, { timeout: 30000 });
    await page.goto("/admin");
    await settle(page);
    await openDemoTools(page);
    await expect(
      page.getByText(/Remaining: 4\/5 Campaign\(s\)/),
    ).toBeVisible({ timeout: 30000 });
    await page.screenshot({
      path: `${SHOTS}/demo-admin-after-delete.png`,
      fullPage: true,
      animations: "disabled",
    });
  });
});
