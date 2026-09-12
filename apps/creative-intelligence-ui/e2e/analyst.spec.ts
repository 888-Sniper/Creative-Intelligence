import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("analyst journey", () => {
  test("employee opens Analyst, sees composer, scope and exports", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.employee, "/analyst");
    await expect(page.getByRole("link", { name: "Analyst" })).toBeVisible();
    await expect(page.getByLabel("Ask Foap Analyst")).toBeVisible();
    const controls = page.locator(".panel", {
      has: page.getByRole("heading", { name: "Analyst Controls" }),
    });
    await expect(controls.getByLabel("Objective")).toBeVisible();
    await expect(controls.getByLabel("Language")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "New Conversation" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Report", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Report XLSX" }),
    ).toBeVisible();
    // The workbook is built server-side on demand: the button fetches
    // it as a blob (parsed errors, no error-pages-saved-as-xlsx), so
    // prove the real download instead of a link href.
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("main").getByRole("button", { name: "Blank Workbook" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("foap-analyst-workbook.xlsx");
  });
});
