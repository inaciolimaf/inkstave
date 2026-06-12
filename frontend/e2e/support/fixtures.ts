/**
 * Shared test fixtures (spec 54).
 *
 * - `runContext`: the two seeded users from global setup.
 * - `apiA` / `apiB`: API clients logged in as User A / User B for fast seeding.
 * - `seedProject`: create a project owned by A with a single `main.tex` whose
 *   content contains "Introduction" (so the agent stub's search finds it).
 *
 * Specs that aren't testing login start from a `storageState` (set per Playwright
 * project), so the browser is already authenticated as User A unless overridden.
 */
import { readFile } from "node:fs/promises";

import { test as base, type Page } from "@playwright/test";

import { ApiClient } from "./api";
import { injectAuth } from "./auth";
import { RUN_CONTEXT_FILE, type RunContext } from "./env";

export const SEED_DOC_CONTENT =
  "\\documentclass{article}\n" +
  "\\begin{document}\n" +
  "\\section{Introduction}\n" +
  "This is the original introduction paragraph.\n" +
  "\\end{document}\n";

export interface SeededProject {
  projectId: string;
  docId: string;
  docName: string;
}

interface Fixtures {
  runContext: RunContext;
  apiA: ApiClient;
  apiB: ApiClient;
  seedProject: (name?: string) => Promise<SeededProject>;
  page: Page;
}

export const test = base.extend<Fixtures>({
  // eslint-disable-next-line no-empty-pattern -- a fixture with no dependencies
  runContext: async ({}, use) => {
    const ctx = JSON.parse(await readFile(RUN_CONTEXT_FILE, "utf-8")) as RunContext;
    await use(ctx);
  },
  // The default page starts authenticated as User A with a fresh refresh token
  // (its own family). The auth journey overrides this with an empty storage state.
  page: async ({ page, context, runContext }, use) => {
    await injectAuth(context, runContext.userA.email);
    await use(page);
  },
  apiA: async ({ runContext }, use) => {
    const client = new ApiClient();
    await client.login(runContext.userA.email);
    await use(client);
  },
  apiB: async ({ runContext }, use) => {
    const client = new ApiClient();
    await client.login(runContext.userB.email);
    await use(client);
  },
  seedProject: async ({ apiA }, use) => {
    await use(async (name = "Paper") => {
      const project = await apiA.createProject(name);
      let doc = await apiA.firstDoc(project.id);
      if (!doc) doc = await apiA.createDoc(project.id, "main.tex");
      await apiA.setDocContent(project.id, doc.id, SEED_DOC_CONTENT);
      return { projectId: project.id, docId: doc.id, docName: doc.name };
    });
  },
});

export { expect } from "@playwright/test";
