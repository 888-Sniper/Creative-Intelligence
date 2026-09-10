import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("employee journey", () => {
  test("signed out sees login, employee sees dashboard, profile, logout", async ({ page, context }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome to Creative Intelligence" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    // No dashboard behind the gate.
    await expect(page.getByRole("link", { name: "Overview" })).toHaveCount(0);

    const seeds = readSeeds();
    await loginAs(context, page, seeds.employee);
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    await expect(page.getByText("Ada L")).toBeVisible();

    await page.getByRole("link", { name: "Profile" }).click();
    await expect(page.getByRole("heading", { name: "Profile" }).first()).toBeVisible();
    // Verified email is shown read-only: visible text, never an editable field.
    await expect(page.getByText("ada@foap.test")).toBeVisible();
    await expect(page.getByRole("textbox", { name: /email/i })).toHaveCount(0);

    await page.getByRole("button", { name: "Log out", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Welcome to Creative Intelligence" })).toBeVisible();
  });

  test("pending employee sees pending gate and no dashboard", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.pending);
    await expect(page.getByRole("heading", { name: "Access pending" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Overview" })).toHaveCount(0);
    await expect(page.getByText("Campaigns")).toHaveCount(0);
  });

  test("settings shows account, provider, appearance and logout-all", async ({ page, context }) => {
    const seeds = readSeeds();
    // NOTE: the admin session (the employee session is destroyed by the
    // logout step of the first journey in this file).
    await loginAs(context, page, seeds.admin, "/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await expect(page.getByText("boss@foap.test (verified, read-only)")).toBeVisible();
    await expect(page.getByRole("radio", { name: /System/ })).toBeVisible();
    page.on("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Log out all sessions" }).click();
    // Revoking includes the current session, so the gate returns to login.
    await expect(page.getByRole("heading", { name: "Welcome to Creative Intelligence" })).toBeVisible();
  });
});
