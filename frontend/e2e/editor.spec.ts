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
const PROJECT = {
  id: "p1",
  name: "Paper",
  owner_id: "u1",
  root_doc_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const TREE = {
  root: {
    id: "root",
    project_id: "p1",
    parent_id: null,
    type: "folder",
    name: "root",
    is_root: true,
    path: "",
    children: [
      {
        id: "main",
        project_id: "p1",
        parent_id: "root",
        type: "doc",
        name: "main.tex",
        is_root: false,
        path: "main.tex",
        children: null,
      },
    ],
  },
};
const CONTENT = "\\documentclass{article}\n\\begin{document}\nHello world\n\\end{document}";

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

test("editor: open a doc, see highlighting, read-only, change font size", async ({ page }) => {
  await page.route("**/api/v1/auth/login", (r) => r.fulfill(json(PAIR)));
  await page.route("**/api/v1/users/me", (r) => r.fulfill(json(USER)));
  await page.route("**/api/v1/projects**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/projects") return route.fulfill(json({ items: [PROJECT], total: 1 }));
    if (path === "/api/v1/projects/p1") return route.fulfill(json(PROJECT));
    if (path === "/api/v1/projects/p1/tree") return route.fulfill(json(TREE));
    if (path === "/api/v1/projects/p1/documents/main") {
      return route.fulfill(
        json({
          entity_id: "main",
          project_id: "p1",
          version: 1,
          size_bytes: CONTENT.length,
          content: CONTENT,
          updated_at: "2026-01-01T00:00:00Z",
        }),
      );
    }
    return route.fulfill(json({ detail: "nf" }, 404));
  });

  // Log in and open the project.
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password", { exact: true }).fill("secret123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.getByRole("link", { name: "Paper" }).click();

  // Open main.tex in the editor.
  await page.getByText("main.tex").click();
  const content = page.locator(".cm-content");
  await expect(content).toContainText("documentclass");
  await expect(page.locator(".cm-gutters")).toBeVisible();
  await expect(page.locator(".cm-lineNumbers")).toContainText("1");
  // Highlighting: at least one token span rendered.
  expect(await page.locator(".cm-line span").count()).toBeGreaterThan(0);
  // The editor is editable (spec 19); a save-status badge is shown.
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // Change the font size; it applies live to the editor.
  await page.getByRole("button", { name: "Editor settings" }).click();
  await page.getByRole("combobox", { name: "Font size" }).click();
  await page.getByRole("option", { name: "20px" }).click();
  await expect
    .poll(() => page.locator(".cm-editor").evaluate((el) => getComputedStyle(el).fontSize))
    .toBe("20px");
});
