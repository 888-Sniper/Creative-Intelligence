import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("providers admin page", () => {
  test("admin sees Providers above Admin/Settings and the blocked ChatGPT card", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/providers");
    await expect(page.getByRole("heading", { name: "Providers", exact: true })).toBeVisible();

    const names = await page.locator(".side-nav a").allTextContents();
    const providersAt = names.indexOf("Providers");
    const adminAt = names.indexOf("Admin");
    const settingsAt = names.indexOf("Settings");
    expect(providersAt).toBeGreaterThanOrEqual(0);
    expect(adminAt).toBeGreaterThanOrEqual(0);
    expect(settingsAt).toBeGreaterThanOrEqual(0);
    expect(providersAt).toBeLessThan(adminAt);
    expect(adminAt).toBeLessThan(settingsAt);

    // Server-driven unsupported entry: listed with its reason, no actions.
    const chatgpt = page.locator("section", { hasText: "ChatGPT" }).last();
    await expect(chatgpt).toBeVisible();
    await expect(chatgpt.getByText(/unofficial API|unsupported/i).first()).toBeVisible();
    await expect(chatgpt.getByRole("button")).toHaveCount(0);
  });

  test("employee sees no Providers item and direct /providers is denied", async ({
    page,
    context,
  }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.employee, "/");
    await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Providers" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
    await page.goto("/providers");
    await expect(page.getByText("Admin Access Required.")).toBeVisible();
  });
});
