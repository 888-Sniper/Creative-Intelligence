import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("providers admin page", () => {
  test("admin sees Providers above Admin/Settings with logos and no unavailable cards", async ({
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

    // Server-flagged unsupported entries are hidden from the list.
    const retired = page.locator("section", {
      has: page.locator("h2", { hasText: /ChatGPT|DeepSeek|Kimi/ }),
    });
    await expect(retired).toHaveCount(0);

    // Supported providers show a brand logo left of the card title.
    const groq = page.locator("section", {
      has: page.locator("h2", { hasText: "Groq" }),
    }).last();
    await expect(groq.locator("img.provider-logo")).toBeVisible();
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
