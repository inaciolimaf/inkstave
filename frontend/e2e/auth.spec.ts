/**
 * Journey 1 — Auth (spec 54 §5.3). Real-stack: register a brand-new user through
 * the UI, land authenticated, log out, log back in; protected routes require auth.
 *
 * This is the one spec that drives register/login through the UI, so it starts
 * from a clean (unauthenticated) browser rather than the shared storage-state.
 */
// Uses the *base* test (no auto-auth fixture): the auth journey must start from a
// clean, unauthenticated browser and drive register/login through the UI itself.
import { expect, test } from "@playwright/test";

import { uniqueId } from "./support/api";
import { E2E_PASSWORD } from "./support/env";
import { DashboardPage, LoginPage } from "./support/pages";

test("register → land authenticated → log out → log back in @smoke", async ({ page }) => {
  const email = `${uniqueId("auth")}@example.com`;
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);

  // Protected route bounces to /login when unauthenticated. ("/" is now the
  // public landing page, so probe a genuinely protected route instead.)
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login$/);

  // Register via the UI → redirected to login with a confirmation.
  await login.gotoRegister();
  await expect(page).toHaveURL(/\/register$/);
  await login.register("E2E User", email, E2E_PASSWORD);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(/account created/i)).toBeVisible();

  // Log in → the protected dashboard.
  await login.login(email, E2E_PASSWORD);
  await expect(page).toHaveURL(/\/projects$/);
  await expect(dashboard.heading()).toBeVisible();

  // Log out → back to the public login page.
  await dashboard.logout();
  await expect(page).toHaveURL(/\/login$/);

  // Protected route still requires auth after logout.
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login$/);

  // Log back in → dashboard again.
  await login.login(email, E2E_PASSWORD);
  await expect(dashboard.heading()).toBeVisible();
});
