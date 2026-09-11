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
    await page.keyboard.press("Escape");
    await expect(page.getByRole("tooltip")).toHaveCount(0);

    // Same non-date filter applies to both windows (TikTok only:
    // 12500 vs 10000 is still +25%, not diluted by Meta rows).
    await page.locator(".filter-bar").getByLabel("Platform").selectOption("tiktok");
    await expect(page.getByText("12,500")).toBeVisible();
    await expect(page.getByText("+25%", { exact: true })).toHaveCount(2);
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
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth <= window.innerWidth + 1,
    );
    expect(overflow).toBe(true);
    });
  });
});
