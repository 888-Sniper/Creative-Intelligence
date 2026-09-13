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
 *  machines, so a pixel gate would be flaky. The review gate is human
 *  side-by-side comparison (see docs/Visual Review.md): the screenshots
 *  under test-results/screens/ are the reviewable artifact, the
 *  assertions below are the deterministic gate.
 *
 *  Approved viewports: 1440x1000 desktop; 1280x800, 1024x768 and
 *  768x1024 responsive passes over all 14 routes; 390x844 mobile
 *  (key routes).
 */
const SHOTS = "test-results/screens";

type Route = [shot: string, path: string, heading: string | RegExp];

const ROUTES: Route[] = [
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

async function expectNoOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

async function expectRoute(page: Page, path: string, heading: string | RegExp) {
  await page.goto(path);
  if (typeof heading === "string") {
    await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
  } else {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
  // Best effort: let charts/tables populate before the capture.
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await expectNoOverflow(page);
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

  for (const [shot, path, heading] of ROUTES) {
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

test.describe("approved screens at responsive viewports", () => {
  // One login per viewport, then every route in the same session:
  // heading composition + no horizontal overflow + capture each.
  const viewports = [
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
    { width: 768, height: 1024 },
  ];

  for (const vp of viewports) {
    test(`all routes at ${vp.width}x${vp.height}`, async ({ page, context }) => {
      test.setTimeout(240000);
      const seeds = readSeeds();
      await loginAs(context, page, seeds.admin, ROUTES[0][1]);
      await page.setViewportSize(vp);
      for (const [shot, path, heading] of ROUTES) {
        await expectRoute(page, path, heading);
        await page.screenshot({
          path: `${SHOTS}/${shot}-${vp.width}.png`,
          fullPage: true,
          animations: "disabled",
        });
      }
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

  // Every route at mobile width: one login, then each route in the
  // same session (heading + no-overflow + capture each).
  const mobileRoutes: Array<[shot: string, path: string, heading: string | RegExp]> = [
    ["m-dashboard", "/", /Good (Morning|Afternoon|Evening),/],
    ["m-campaigns", "/campaigns", "Campaigns"],
    ["m-creatives", "/creatives", "Creatives"],
    ["m-compare", "/compare", "Compare"],
    ["m-benchmarks", "/benchmarks", "Benchmarks Library"],
    ["m-insights", "/insights", "Saved Insights"],
    ["m-reports", "/reports", "Generated Reports"],
    ["m-workbook", "/workbook", "Blank Workbook"],
    ["m-ask", "/ask", "Ask The Data"],
    ["m-analyst", "/analyst", "Your Creative Partner"],
    ["m-admin", "/admin", "Admin"],
    ["m-profile", "/profile", "Profile"],
    ["m-settings", "/settings", "Settings"],
  ];

  test("all routes fit without overflow", async ({ page, context }) => {
    test.setTimeout(240000);
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, mobileRoutes[0][1]);
    for (const [shot, path, heading] of mobileRoutes) {
      await page.goto(path);
      if (typeof heading === "string") {
        await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
      } else {
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      }
      await expectNoOverflow(page);
      await page.screenshot({ path: `${SHOTS}/${shot}.png`, fullPage: true, animations: "disabled" });
    }
  });
});
