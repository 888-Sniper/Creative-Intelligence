import { expect, test } from "@playwright/test";
import { loginAs, readSeeds } from "./helpers";

test.describe("employee journey", () => {
  test("employee login matches the approved Foap design", async ({ page }) => {
    await page.goto("/");
    const card = page.locator(".login-card");
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    await expect(page.getByText("Sign In To Your Employee Workspace.")).toBeVisible();
    // No Creative Intelligence product branding on the login screen.
    await expect(page.getByText("Creative Intelligence")).toHaveCount(0);
    // Foap logo centred above the card.
    const logo = page.getByAltText("Foap");
    await expect(logo).toBeVisible();
    const logoBox = await logo.boundingBox();
    const cardBox = await card.boundingBox();
    expect(logoBox).not.toBeNull();
    expect(cardBox).not.toBeNull();
    expect(logoBox!.y + logoBox!.height).toBeLessThanOrEqual(cardBox!.y);
    const viewport = page.viewportSize()!;
    const cardCenter = cardBox!.x + cardBox!.width / 2;
    const logoCenter = logoBox!.x + logoBox!.width / 2;
    expect(Math.abs(cardCenter - viewport.width / 2)).toBeLessThanOrEqual(16);
    expect(Math.abs(logoCenter - viewport.width / 2)).toBeLessThanOrEqual(16);
    // Card is a single focused panel, roughly 440–500px wide.
    expect(cardBox!.width).toBeGreaterThanOrEqual(300);
    expect(cardBox!.width).toBeLessThanOrEqual(520);
    // Form controls.
    await expect(page.getByLabel("Work Email")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Password" })).toBeVisible();
    await expect(page.getByText("Remember Me")).toBeVisible();
    await expect(page.getByRole("button", { name: "Forgot Password?" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign In", exact: true })).toBeVisible();
    // Password is masked with a visibility toggle.
    await expect(page.getByRole("textbox", { name: "Password" })).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show Password" }).click();
    await expect(page.getByRole("textbox", { name: "Password" })).toHaveAttribute("type", "text");
    // Only employee SSO providers; code flow hidden behind its control.
    await expect(page.getByRole("button", { name: "Continue With Google" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue With Microsoft" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Continue With Apple" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Continue With GitHub" })).toHaveCount(0);
    await expect(page.getByLabel("Verification Code")).toHaveCount(0);
    await page.getByRole("button", { name: "Use A Sign-In Code Instead" }).click();
    await expect(page.getByRole("button", { name: "Send Sign-In Code" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Password" })).toHaveCount(0);
    await page.getByRole("button", { name: "Back To Password Sign In" }).click();
    await expect(page.getByRole("textbox", { name: "Password" })).toBeVisible();
    // Employee-only footer, no signup.
    await expect(page.getByText("For Foap employees only.", { exact: false })).toBeVisible();
    await expect(page.getByText(/create account/i)).toHaveCount(0);
    await expect(page.getByText(/sign up/i)).toHaveCount(0);
    // No dashboard behind the gate.
    await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  });

  test("failed password sign-in shows a clean inline error", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    await page.getByLabel("Work Email").fill("nobody@foap.test");
    await page.getByRole("textbox", { name: "Password" }).fill("wrong-password");
    await page.getByRole("button", { name: "Sign In", exact: true }).click();
    const status = page.getByRole("status");
    await expect(status).not.toBeEmpty();
    // Still on the branded login card, no raw internals.
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    await expect(status).not.toContainText(/traceback|secret|exception/i);
  });

  test("signed out sees login, employee sees dashboard, profile, logout", async ({ page, context }) => {
    await page.goto("/");
    // Light default with no saved choice: the pre-render script leaves
    // the theme unset before first paint (no dark flash), React keeps
    // it. (Approved default flipped dark -> light; a stored "dark"
    // still wins.)
    expect(await page.evaluate(() => document.documentElement.dataset["theme"] ?? "")).toBe("");
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
    // No dashboard behind the gate.
    await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);

    const seeds = readSeeds();
    await loginAs(context, page, seeds.employee);
    // Approved Dashboard greets by daypart: "Good Morning, Ada".
    await expect(page.getByRole("heading", { name: /Good (Morning|Afternoon|Evening),/ })).toBeVisible();
    // Approved browser title is exactly "Creative Intelligence".
    await expect(page).toHaveTitle("Creative Intelligence");
    await expect(page.getByText("Ada L")).toBeVisible();

    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings", exact: true }).first()).toBeVisible();
    // Email is shown read-only (bare address, no verified suffix): hero,
    // Workspace, and Connections surfaces carry it, never an editable field.
    await expect(page.getByText("ada@foap.test", { exact: true })).toHaveCount(3);
    await expect(page.getByRole("textbox", { name: /email/i })).toHaveCount(0);
    // The old Profile route redirects to the merged Settings page.
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { name: "Settings", exact: true }).first()).toBeVisible();

    // The account menu ships collapsed; expand it to reach Log Out
    // (scoped: Settings Security carries its own adaptive Log Out now).
    await page.getByRole("button", { name: "Toggle Account Menu" }).click();
    await page.locator("#account-menu-body").getByRole("button", { name: "Log Out", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
  });

  test.describe("mobile login", () => {
    test.use({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });

    test("login fits without horizontal overflow and stays centred", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
      const cardBox = await page.locator(".login-card").boundingBox();
      const logoBox = await page.getByAltText("Foap").boundingBox();
      expect(cardBox).not.toBeNull();
      expect(logoBox).not.toBeNull();
      expect(Math.abs(cardBox!.x + cardBox!.width / 2 - 195)).toBeLessThanOrEqual(16);
      expect(logoBox!.y + logoBox!.height).toBeLessThanOrEqual(cardBox!.y);
      await expect(page.getByRole("button", { name: "Sign In", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Continue With Google" })).toBeVisible();
    });
  });

  test("account menu collapses so it cannot cover page controls", async ({ page, context }) => {
    const seeds = readSeeds();
    // NOTE: the admin session — the employee session is destroyed by
    // the logout step of the first journey in this file.
    await loginAs(context, page, seeds.admin);
    // Approved Dashboard greets by daypart: "Good Morning, Ada".
    await expect(page.getByRole("heading", { name: /Good (Morning|Afternoon|Evening),/ })).toBeVisible();
    const toggle = page.getByRole("button", { name: "Toggle Account Menu" });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("button", { name: "Log Out", exact: true })).toHaveCount(0);
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("button", { name: "Log Out", exact: true })).toBeVisible();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByRole("button", { name: "Log Out", exact: true })).toHaveCount(0);
  });

  test("pending employee sees pending gate and no dashboard", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.pending);
    await expect(page.getByRole("heading", { name: "Access Pending" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
    await expect(page.getByText("Campaigns")).toHaveCount(0);
  });

  test("settings shows Google Drive card unconnected (item 31)", async ({ page, context }) => {
    const seeds = readSeeds();
    await loginAs(context, page, seeds.admin, "/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Google Drive" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeVisible();
    // E2E has no Google credentials: the server says so instead of bouncing.
    // Plain click: the collapsed account menu cannot intercept it.
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.getByText("Google Drive is not configured.")).toBeVisible();
  });

  test("settings shows identity, appearance and logout-all", async ({ page, context }) => {
    const seeds = readSeeds();
    // NOTE: the admin session (the employee session is destroyed by the
    // logout step of the first journey in this file).
    await loginAs(context, page, seeds.admin, "/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    // Merged page: the account identity lives here (hero, Workspace,
    // Connections) with no separate Profile destination.
    await expect(page.getByText("boss@foap.test", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Profile" })).toHaveCount(0);
    // Reskinned appearance control is a Theme select with a System option.
    await expect(page.getByLabel("Theme")).toBeVisible();
    await expect(page.getByLabel("Theme").locator("option", { hasText: "System" })).toHaveCount(1);
    // Exactly one adaptive logout control, labelled by the server count
    // (Log Out for a single session, Log Out All Sessions otherwise —
    // earlier specs may legitimately leave extra admin sessions).
    // Signing out returns the gate to login.
    const logoutAll = page.getByRole("button", { name: "Log Out All Sessions" });
    const logoutOne = page.getByRole("button", { name: "Log Out", exact: true });
    const shown = await logoutAll.count() + await logoutOne.count();
    expect(shown).toBe(1);
    page.on("dialog", (d) => void d.accept());
    if (await logoutAll.count()) {
      await logoutAll.click();
    } else {
      await logoutOne.click();
    }
    await expect(page.getByRole("heading", { name: "Welcome Back" })).toBeVisible();
  });
});
