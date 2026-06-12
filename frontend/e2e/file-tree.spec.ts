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

interface WE {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: "folder" | "doc" | "file";
  name: string;
  is_root: boolean;
  path: string;
}

function json(body: unknown, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

function buildTree(entities: WE[]): unknown {
  const build = (n: WE): unknown => ({
    ...n,
    children: entities.filter((e) => e.parent_id === n.id).map(build),
  });
  return build(entities.find((e) => e.is_root)!);
}

test("file tree: create folder + doc, rename, move, upload, delete", async ({ page }) => {
  let entities: WE[] = [
    {
      id: "root",
      project_id: "p1",
      parent_id: null,
      type: "folder",
      name: "root",
      is_root: true,
      path: "",
    },
    {
      id: "main",
      project_id: "p1",
      parent_id: "root",
      type: "doc",
      name: "main.tex",
      is_root: false,
      path: "main.tex",
    },
  ];
  let counter = 0;

  await page.route("**/api/v1/auth/login", (r) => r.fulfill(json(PAIR)));
  await page.route("**/api/v1/users/me", (r) => r.fulfill(json(USER)));

  await page.route("**/api/v1/projects**", async (route) => {
    const req = route.request();
    const method = req.method();
    const path = new URL(req.url()).pathname;

    if (path === "/api/v1/projects" && method === "GET") {
      return route.fulfill(
        json({
          items: [
            {
              id: "p1",
              name: "Paper",
              owner_id: "u1",
              root_doc_id: null,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      );
    }
    if (path === "/api/v1/projects/p1" && method === "GET") {
      return route.fulfill(
        json({
          id: "p1",
          name: "Paper",
          owner_id: "u1",
          root_doc_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        }),
      );
    }
    if (path === "/api/v1/projects/p1/tree" && method === "GET") {
      return route.fulfill(json({ root: buildTree(entities) }));
    }
    if (path === "/api/v1/projects/p1/tree/entities" && method === "POST") {
      const body = req.postDataJSON() as {
        type: WE["type"];
        name: string;
        parent_id: string | null;
      };
      const ent: WE = {
        id: `e${++counter}`,
        project_id: "p1",
        parent_id: body.parent_id ?? "root",
        type: body.type,
        name: body.name,
        is_root: false,
        path: body.name,
      };
      entities.push(ent);
      return route.fulfill(json(ent, 201));
    }
    const rn = path.match(/\/tree\/entities\/([^/]+)\/rename$/);
    if (rn && method === "PATCH") {
      const body = req.postDataJSON() as { name: string };
      entities = entities.map((e) => (e.id === rn[1] ? { ...e, name: body.name } : e));
      return route.fulfill(json(entities.find((e) => e.id === rn[1])));
    }
    const mv = path.match(/\/tree\/entities\/([^/]+)\/move$/);
    if (mv && method === "PATCH") {
      const body = req.postDataJSON() as { new_parent_id: string };
      entities = entities.map((e) =>
        e.id === mv[1] ? { ...e, parent_id: body.new_parent_id } : e,
      );
      return route.fulfill(json(entities.find((e) => e.id === mv[1])));
    }
    if (path === "/api/v1/projects/p1/files" && method === "POST") {
      const ent: WE = {
        id: `f${++counter}`,
        project_id: "p1",
        parent_id: "root",
        type: "file",
        name: "pic.png",
        is_root: false,
        path: "pic.png",
      };
      entities.push(ent);
      return route.fulfill(json(ent, 201));
    }
    const del = path.match(/\/tree\/entities\/([^/]+)$/);
    if (del && method === "DELETE") {
      entities = entities.filter((e) => e.id !== del[1] && e.parent_id !== del[1]);
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill(json({ detail: "nf" }, 404));
  });

  // Log in and open the project.
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password", { exact: true }).fill("secret123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.getByRole("link", { name: "Paper" }).click();
  await expect(page).toHaveURL(/\/projects\/p1$/);
  await expect(page.getByRole("treeitem", { name: /main\.tex/ })).toBeVisible();

  // Create a folder.
  await page.getByRole("button", { name: "New folder" }).click();
  await page.getByLabel("Name").fill("chapters");
  await page.getByRole("button", { name: "Create" }).click();
  const folderRow = page.getByRole("treeitem", { name: /chapters/ });
  await expect(folderRow).toBeVisible();

  // Create a doc inside the folder via its row menu.
  await folderRow.getByRole("button", { name: "Actions for chapters" }).click();
  await page.getByRole("menuitem", { name: "New file" }).click();
  await page.getByLabel("Name").fill("intro.tex");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("treeitem", { name: /intro\.tex/ })).toBeVisible();

  // Rename it.
  const docRow = page.getByRole("treeitem", { name: /intro\.tex/ });
  await docRow.getByRole("button", { name: "Actions for intro.tex" }).click();
  await page.getByRole("menuitem", { name: "Rename" }).click();
  await page.getByLabel("New name").fill("introduction.tex");
  await page.getByLabel("New name").press("Enter");
  await expect(page.getByRole("treeitem", { name: /introduction\.tex/ })).toBeVisible();

  // Move it to root.
  const renamed = page.getByRole("treeitem", { name: /introduction\.tex/ });
  await renamed.getByRole("button", { name: "Actions for introduction.tex" }).click();
  await page.getByRole("menuitem", { name: "Move to root" }).click();
  await expect(page.getByText("Moved")).toBeVisible();

  // Upload a small binary into the tree.
  await page.locator('input[type="file"]').setInputFiles({
    name: "pic.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47]),
  });
  await expect(page.getByRole("treeitem", { name: /pic\.png/ })).toBeVisible();

  // Delete the folder.
  await folderRow.getByRole("button", { name: "Actions for chapters" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("treeitem", { name: /chapters/ })).toHaveCount(0);
});
