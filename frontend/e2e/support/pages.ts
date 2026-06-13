/**
 * Page objects for the recurring surfaces (spec 54 §5.2).
 *
 * Selectors here mirror the real components' roles/labels so specs read as user
 * stories and stay maintainable. Each wraps a Playwright `Page`.
 */
import { expect, type Locator, type Page } from "@playwright/test";

/** Escape a string for safe embedding in a RegExp (project names contain spaces/parens). */
function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/login");
  }

  async login(email: string, password: string): Promise<void> {
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password", { exact: true }).fill(password);
    await this.page.getByRole("button", { name: /sign in/i }).click();
  }

  async gotoRegister(): Promise<void> {
    await this.page.getByRole("link", { name: /create one/i }).click();
  }

  async register(displayName: string, email: string, password: string): Promise<void> {
    await this.page.getByLabel("Display name").fill(displayName);
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password", { exact: true }).fill(password);
    await this.page.getByLabel("Confirm password").fill(password);
    await this.page.getByRole("button", { name: /create account/i }).click();
  }
}

export class DashboardPage {
  constructor(private readonly page: Page) {}

  heading(): Locator {
    return this.page.getByRole("heading", { name: "Your projects" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/projects");
    await expect(this.heading()).toBeVisible();
  }

  async createProject(name: string): Promise<void> {
    await this.page.getByRole("button", { name: /new project/i }).click();
    await this.page.getByLabel("Project name").fill(name);
    await this.page.getByRole("button", { name: "Create" }).click();
  }

  projectLink(name: string): Locator {
    return this.page.getByRole("link", { name });
  }

  /** The table row for one project (scoped so parallel specs don't collide). */
  row(name: string): Locator {
    return this.page.getByRole("row", { name: new RegExp(escapeRe(name)) });
  }

  async open(name: string): Promise<void> {
    await this.projectLink(name).click();
  }

  async rename(from: string, to: string): Promise<void> {
    await this.row(from).getByRole("button", { name: "Project actions" }).click();
    await this.page.getByRole("menuitem", { name: "Rename" }).click();
    await this.page.getByLabel("Project name").fill(to);
    await this.page.getByRole("button", { name: "Save" }).click();
  }

  async delete(name: string): Promise<void> {
    await this.row(name).getByRole("button", { name: "Project actions" }).click();
    await this.page.getByRole("menuitem", { name: "Delete" }).click();
    await this.page.getByRole("button", { name: "Delete" }).click();
  }

  async logout(): Promise<void> {
    await this.page.getByRole("button", { name: /log out/i }).click();
  }
}

export class EditorPage {
  constructor(private readonly page: Page) {}

  async open(projectId: string): Promise<void> {
    await this.page.goto(`/projects/${projectId}`);
  }

  content(): Locator {
    return this.page.locator(".cm-content");
  }

  /** The CodeMirror editor root — its computed font-size reflects the font setting. */
  editorRoot(): Locator {
    return this.page.locator(".cm-editor");
  }

  /** Line-number gutter elements (rendered by the `lineNumbers()` extension). */
  lineNumbers(): Locator {
    return this.page.locator(".cm-lineNumbers .cm-gutterElement");
  }

  /** Syntax-highlight token spans inside the rendered lines. */
  tokenSpans(): Locator {
    return this.page.locator(".cm-line span");
  }

  /** Open the in-editor settings popover (gear button). */
  async openSettings(): Promise<void> {
    await this.page.getByRole("button", { name: "Editor settings" }).click();
  }

  /** Pick a font size from the open settings popover (e.g. "24"). */
  async setFontSize(px: number): Promise<void> {
    await this.page.getByLabel("Font size").click();
    await this.page.getByRole("option", { name: `${px}px` }).click();
  }

  /** The "online now" presence list in the collab editor toolbar. */
  presenceList(): Locator {
    return this.page.getByRole("list", { name: "People online" });
  }

  /** A presence avatar for a specific collaborator by display name. */
  presenceOf(displayName: string): Locator {
    return this.page.getByLabel(`${displayName} — online`);
  }

  /** A remote collaborator's cursor caret in the editor (y-codemirror.next). */
  remoteCursor(): Locator {
    return this.page.locator(".cm-ySelectionCaret");
  }

  /** Wait for the live (collab) editor to finish syncing and become editable.
   * Generous budget: a fresh doc's WS handshake + sync is the slowest step under
   * parallel load, so this prevents a flaky 10s timeout (spec 55 de-flake). */
  async waitEditable(timeout = 20_000): Promise<void> {
    await expect(this.page.locator(".cm-content[contenteditable='true']")).toBeVisible({ timeout });
  }

  /** Click a file in the tree by name to open it. */
  async openFile(name: string): Promise<void> {
    await this.page.getByText(name, { exact: true }).first().click();
    await expect(this.content()).toBeVisible();
  }

  async type(text: string): Promise<void> {
    await this.content().click();
    await this.page.keyboard.press("End");
    await this.page.keyboard.type(text);
  }

  savedBadge(): Locator {
    return this.page.getByText("Saved", { exact: true });
  }

  /** The transient "Saving…" badge (REST autosave in-flight); note U+2026 ellipsis. */
  savingBadge(): Locator {
    return this.page.getByText("Saving…", { exact: true });
  }

  /** The REST-autosave status region (only mounted in non-collab/REST mode). */
  saveStatus(): Locator {
    return this.page.getByTestId("save-status");
  }

  unsavedBadge(): Locator {
    return this.page.getByText("Unsaved changes");
  }

  /** A New file button in the tree toolbar (aria-label "New file"). */
  async createFile(name: string): Promise<void> {
    await this.page.getByRole("button", { name: "New file" }).first().click();
    const dialog = this.page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByRole("button", { name: "Create" }).click();
  }
}

export class PreviewPanel {
  constructor(private readonly page: Page) {}

  async compile(): Promise<void> {
    await this.page.getByRole("button", { name: "Compile project" }).click();
  }

  /** A rendered PDF page canvas (PDF.js). */
  firstPage(): Locator {
    return this.page.getByLabel("Page 1");
  }

  /** Compile output is a tabbed region (spec 27): select the "Log" tab. */
  async openLog(): Promise<void> {
    await this.page.getByRole("tab", { name: /log/i }).click();
  }

  /** Select the "Problems" tab of the compile-output region. */
  async openProblems(): Promise<void> {
    await this.page.getByRole("tab", { name: /problems/i }).click();
  }

  logRegion(): Locator {
    return this.page.getByRole("region", { name: "Compile log" });
  }

  /** A problems-panel entry for a given error message substring. */
  problem(message: string): Locator {
    return this.page.getByRole("button", { name: new RegExp(`error: ${message}`, "i") });
  }
}

export class AgentPanel {
  constructor(private readonly page: Page) {}

  async open(): Promise<void> {
    await this.page.getByRole("button", { name: "Agent" }).click();
    // Radix names the dialog after its title, so wait on the composer instead.
    await expect(this.composer()).toBeVisible();
  }

  composer(): Locator {
    return this.page.getByLabel("Message the agent");
  }

  async send(message: string): Promise<void> {
    await this.composer().fill(message);
    await this.page.getByLabel("Send message").click();
  }

  reviewButton(): Locator {
    return this.page.getByRole("button", { name: /Review changes/ });
  }
}

export class DiffReview {
  constructor(private readonly page: Page) {}

  dialog(): Locator {
    return this.page.getByRole("dialog");
  }

  async openFromAgent(): Promise<void> {
    await this.page.getByRole("button", { name: /Review changes/ }).click();
    await expect(this.page.getByText("Review proposed changes")).toBeVisible();
  }

  /** Apply all proposed hunks, confirming the alert dialog. */
  async applyAll(): Promise<void> {
    await this.dialog().getByRole("button", { name: "Apply" }).first().click();
    const confirm = this.page.getByRole("alertdialog");
    await expect(confirm.getByText("Apply changes?")).toBeVisible();
    await confirm.getByRole("button", { name: "Apply" }).click();
  }
}

export class HistoryPanel {
  constructor(private readonly page: Page) {}

  async open(): Promise<void> {
    await this.page.getByRole("button", { name: "History" }).click();
    await expect(this.page.getByText("Version history")).toBeVisible();
  }
}

/** The "Share" modal: invite a collaborator by email + role (spec 33 / 54 §5.2). */
export class ShareDialog {
  constructor(private readonly page: Page) {}

  dialog(): Locator {
    return this.page.getByRole("dialog", { name: "Share project" });
  }

  /** Open the Share modal from the editor toolbar's "Share" button. */
  async open(): Promise<void> {
    await this.page.getByRole("button", { name: "Share" }).click();
    await expect(this.dialog()).toBeVisible();
  }

  /** Fill the invite email, choose a role, and submit (owner-only invite form). */
  async invite(email: string, role: "editor" | "viewer" = "editor"): Promise<void> {
    await this.dialog().getByLabel("Invite by email").fill(email);
    await this.dialog().getByLabel("Invite role").click();
    await this.page.getByRole("option", { name: role === "editor" ? "Editor" : "Viewer" }).click();
    await this.dialog().getByRole("button", { name: "Invite" }).click();
  }

  /** A pending-invite row for an invited email (shown to the owner after inviting). */
  pendingInvite(email: string): Locator {
    return this.dialog().getByText(email, { exact: true });
  }
}
