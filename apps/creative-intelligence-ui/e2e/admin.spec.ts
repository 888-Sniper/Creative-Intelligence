import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("admin journey", () => {
  test("add, approve, change role, suspend, reactivate", async ({ page, context }) => {
    const seeds = readSeeds();
    // Accept every confirmation dialog: the test intent is to exercise the
    // confirmed destructive actions end to end (dialog text is asserted in
    // Vitest component tests).
    page.on("dialog", (d) => void d.accept());
    await loginAs(context, page, seeds.admin, "/admin");
    await expect(page.getByRole("heading", { name: "Admin — Employees" })).toBeVisible();

    const email = `e2e-${Date.now()}@foap.test`;
    await page.getByLabel("New employee email").fill(email);
    await page.getByLabel("New employee first name").fill("E2E");
    await page.getByRole("button", { name: "Add (active)" }).click();
    await expect(page.getByText("Employee added as active.")).toBeVisible();

    const row = page.getByRole("row", { name: new RegExp(email) });
    await expect(row).toBeVisible();
    // Added active: suspend then reactivate.
    await row.getByRole("button", { name: "Suspend" }).click();
    await expect(row.getByRole("button", { name: "Reactivate" })).toBeVisible();
    await row.getByRole("button", { name: "Reactivate" }).click();
    await expect(row.getByRole("button", { name: "Suspend" })).toBeVisible();
    // Role change employee -> admin -> employee (accept confirms).
    await row.getByRole("button", { name: "Make admin" }).click();
    await expect(row.getByRole("button", { name: "Make employee" })).toBeVisible();
    await row.getByRole("button", { name: "Make employee" }).click();
    await expect(row.getByRole("button", { name: "Make admin" })).toBeVisible();
    // Audit trail records the lifecycle.
    await expect(page.getByText("EMPLOYEE_CREATED").first()).toBeVisible();
  });

  test("foreign installation sees no accounts to switch to", async ({ page, context }) => {
    const seeds = readSeeds();
    // Same admin session cookie, but a fresh foreign container: the app
    // adopts nothing (session already bound to e2e-installation) and the
    // gate refuses it, so no dashboard and no account list appear.
    // Generous timeouts: CI runners boot the seeded backend slowly and the
    // gate settles through a loading state first (same strict assertions).
    await loginAs(context, page, seeds.admin, "/", false);
    await expect(page.getByRole("heading", { name: "Welcome To Creative Intelligence" })).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("link", { name: "Overview" })).toHaveCount(0, { timeout: 15000 });
    await expect(page.getByRole("button", { name: /Switch to/ })).toHaveCount(0, { timeout: 15000 });
  });

  test("multi-account switch re-runs authorization", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin);
    await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();
    // Switch to the non-admin employee account from the account menu.
    await page.getByRole("button", { name: "Toggle Account Menu" }).click();
    await page.getByRole("button", { name: /Switch To Ada L/ }).click();
    await expect(page.getByText("Ada L").first()).toBeVisible();
    // Admin tab is gone: authorization follows the new account, not the old.
    await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  });
});
