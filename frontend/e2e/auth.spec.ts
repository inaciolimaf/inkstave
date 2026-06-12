import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "e2e@example.com",
  display_name: "E2E User",
  is_admin: false,
  email_confirmed: false,
  created_at: "2026-01-01T00:00:00Z",
};
const PAIR = { access_token: "AT", refresh_token: "RT", token_type: "bearer", expires_in: 900 };

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

test("register, log in, see home, and log out", async ({ page }) => {
  await page.route("**/api/v1/auth/register", (route) => route.fulfill(json(USER, 201)));
  await page.route("**/api/v1/auth/login", (route) => route.fulfill(json(PAIR)));
  await page.route("**/api/v1/users/me", (route) => route.fulfill(json(USER)));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill(json({ detail: "Logged out." })),
  );
  await page.route("**/api/v1/projects**", (route) => route.fulfill(json({ items: [], total: 0 })));

  // Unauthenticated visit to "/" is bounced to /login.
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  // Register.
  await page.getByRole("link", { name: /create one/i }).click();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByLabel("Display name").fill("E2E User");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password", { exact: true }).fill("secret123");
  await page.getByLabel("Confirm password").fill("secret123");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(/account created/i)).toBeVisible();

  // Log in -> land on the protected projects dashboard.
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password", { exact: true }).fill("secret123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByRole("heading", { name: "Your projects" })).toBeVisible();

  // Log out -> back to /login.
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page).toHaveURL(/\/login$/);
});
