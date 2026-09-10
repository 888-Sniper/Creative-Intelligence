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
    const controls = page.locator(".analyst-controls");
    await expect(controls.getByLabel("Objective")).toBeVisible();
    await expect(controls.getByLabel("Language")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "New conversation" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Report", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Report XLSX" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Blank workbook" }),
    ).toHaveAttribute("href", "/api/analyst/workbook");
  });
});
