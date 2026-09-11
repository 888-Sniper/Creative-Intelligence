import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

/** Real previous-period KPI comparisons on deterministic seeded data.

 *  Seed weeks: current 2024-01-01..2024-01-07 vs previous
 *  2023-12-25..2023-12-31 (impressions 25000 vs 20000 = +25%).
 */
test.describe("kpi period comparison", () => {
  test("dashboard trends, tooltip, date change and filters", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.kpi, "/");
    await expect(page.getByText("45,000")).toBeVisible();

    // Default dataset extent has an empty previous window: honest
    // no-comparison state, no trend arrows anywhere.
    await expect(
      page.getByRole("button", { name: "Explain Comparison Period" }),
    ).toHaveCount(0);

    // Selecting a real range recalculates both periods.
    await page.getByLabel("From date").fill("2024-01-01");
    await page.getByLabel("To date").fill("2024-01-07");
    await expect(page.getByText("25,000")).toBeVisible();
    // Both weekly windows are in scope: impressions and CPA each +25%.
    await expect(
      page.getByRole("button", { name: "Explain Comparison Period" }),
    ).not.toHaveCount(0);
    await expect(page.getByText("+25%", { exact: true })).toHaveCount(2);

    // Hover opens the tooltip with the exact previous range.
    const info = page
      .getByRole("button", { name: "Explain Comparison Period" })
      .first();
    await info.hover();
    await expect(page.getByRole("tooltip")).toContainText(
      "Dec 25 – Dec 31, 2023",
    );

    // Keyboard: focus opens, Escape closes.
    await info.focus();
    await expect(page.getByRole("tooltip")).toBeVisible();
    // Anchored to the info icon itself: the popup sits ~6px above
    // the button, centered on it — never over the arrow/percentage.
    const tipBox = await page.getByRole("tooltip").boundingBox();
    const btnBox = await info.boundingBox();
    expect(tipBox).not.toBeNull();
    expect(btnBox).not.toBeNull();
    const gap = btnBox!.y - tipBox!.y - tipBox!.height;
    expect(gap).toBeGreaterThanOrEqual(3);
    expect(gap).toBeLessThanOrEqual(12);
    const tipCenter = tipBox!.x + tipBox!.width / 2;
    const btnCenter = btnBox!.x + btnBox!.width / 2;
    expect(Math.abs(tipCenter - btnCenter)).toBeLessThanOrEqual(4);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);

    // Same non-date filter applies to both windows (TikTok only:
    // 12500 vs 10000 is still +25%, not diluted by Meta rows).
    await page.locator(".filter-bar").getByLabel("Platform").selectOption("tiktok");
    await expect(page.getByText("12,500")).toBeVisible();
    await expect(page.getByText("+25%", { exact: true })).toHaveCount(2);

    // An exact Date pins a one-day current period (Jan 5 here, whose
    // previous day has no rows): graceful no-comparison state.
    await page.getByRole("button", { name: "Clear Filters" }).click();
    await page.locator(".filter-bar").getByLabel("Date", { exact: true }).fill("2024-01-05");
    await expect(page.getByText("12,500")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Explain Comparison Period" }),
    ).toHaveCount(0);
  });

  test.describe("mobile", () => {
    test.use({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });

    test("tap opens tooltip without overflow", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.kpi, "/");
    await page.getByLabel("From date").fill("2024-01-01");
    await page.getByLabel("To date").fill("2024-01-07");
    await expect(page.getByText("25,000")).toBeVisible();
    await expect(page.getByText("+25%", { exact: true }).first()).toBeVisible();
    await page
      .getByRole("button", { name: "Explain Comparison Period" })
      .first()
      .tap();
    await expect(page.getByRole("tooltip")).toContainText(
      "Dec 25 – Dec 31, 2023",
    );
    // On-screen, not merely in the DOM: wait until the box sits
    // inside the viewport (a fixed tooltip with document-based `top`
    // would pass toBeVisible while rendering far below the screen).
    await page.waitForFunction(() => {
      const tip = document.querySelector('[role="tooltip"]');
      if (!tip) return false;
      const r = tip.getBoundingClientRect();
      return (
        r.width > 0 &&
        r.top >= 0 &&
        r.bottom <= window.innerHeight &&
        r.left >= 0 &&
        r.right <= window.innerWidth
      );
    });
    const box = await page.getByRole("tooltip").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(844);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth <= window.innerWidth + 1,
    );
    expect(overflow).toBe(true);
    });
  });
});
