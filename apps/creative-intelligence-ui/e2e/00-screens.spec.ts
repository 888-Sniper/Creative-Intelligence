import { expect, test, type Page } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** 14-screen approved-product composition + capture suite.
 *
 *  ORDERING: this file must sort before auth.spec.ts — that spec's
 *  "log out all sessions" journey destroys the seeded admin session
 *  token these captures plant. (Single worker, alphabetical file
 *  order; same convention as account-switch.spec.ts.)
 *
 *  For every approved route this suite proves the specified composition
 *  (sidebar shell, page heading, no horizontal overflow) and captures a
 *  full-page screenshot under test-results/screens/ for human
 *  side-by-side comparison against the approved references. Pixel
 *  assertions are deliberately absent: font rendering differs between
 *  developer machines and CI runners, so a pixel gate would be flaky;
 *  the screenshots are the reviewable artifact, the assertions below
 *  are the deterministic gate.
 *
 *  Approved viewports: 1440x1000 desktop, 390x844 mobile (key routes).
 */
const SHOTS = "test-results/screens";

async function expectNoOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test.describe("approved screens at desktop viewport", () => {
  test.use({ viewport: { width: 1440, height: 1000 } });

  test("01 employee login", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    await expect(page.getByText("Sign In To Your Employee Workspace.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign In", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue With Google" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue With Microsoft" })).toBeVisible();
    await expectNoOverflow(page);
    await page.screenshot({ path: `${SHOTS}/01-login.png`, animations: "disabled" });
  });

  const routes: Array<[shot: string, path: string, heading: string | RegExp]> = [
    ["02-dashboard", "/", /Good (Morning|Afternoon|Evening),/],
    ["03-campaigns", "/campaigns", "Campaigns"],
    ["04-creatives", "/creatives", "Creatives"],
    ["05-compare", "/compare", "Compare"],
    ["06-benchmarks", "/benchmarks", "Benchmarks Library"],
    ["07-insights", "/insights", "Saved Insights"],
    ["08-reports", "/reports", "Generated Reports"],
    ["09-workbook", "/workbook", "Blank Workbook"],
    ["10-ask", "/ask", "Ask The Data"],
    ["11-analyst", "/analyst", "Your Creative Partner"],
    ["12-admin", "/admin", "Admin"],
    ["13-profile", "/profile", "Profile"],
    ["14-settings", "/settings", "Settings"],
  ];

  for (const [shot, path, heading] of routes) {
    test(`${shot} ${path}`, async ({ page, context }) => {
      const seeds = readSeeds();
      await loginAs(context, page, seeds.admin, path);
      if (typeof heading === "string") {
        await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
      } else {
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      }
      // Active product shell on every route: sidebar + topbar search.
      await expect(page.getByRole("link", { name: "Dashboard", exact: true })).toBeVisible();
      await expect(page.getByRole("search")).toBeVisible();
      // Best effort: let charts/tables populate before the capture.
      await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
      await expectNoOverflow(page);
      await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true, animations: "disabled" });
    });
  }
});

test.describe("approved screens at mobile viewport", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("login fits without overflow", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    await expectNoOverflow(page);
    await page.screenshot({ path: `${SHOTS}/m-login.png`, animations: "disabled" });
  });

  const mobileRoutes: Array<[shot: string, path: string, heading: string | RegExp]> = [
    ["m-dashboard", "/", /Good (Morning|Afternoon|Evening),/],
    ["m-compare", "/compare", "Compare"],
    ["m-analyst", "/analyst", "Your Creative Partner"],
  ];

  for (const [shot, path, heading] of mobileRoutes) {
    test(`${shot} ${path}`, async ({ page, context }) => {
      const seeds = readSeeds();
      await loginAs(context, page, seeds.admin, path);
      if (typeof heading === "string") {
        await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
      } else {
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      }
      await expectNoOverflow(page);
      await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true, animations: "disabled" });
    });
  }
});
