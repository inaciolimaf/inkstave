/**
 * Shared test fixtures (spec 54).
 *
 * - `runContext`: the two seeded users from global setup.
 * - `apiA` / `apiB`: API clients for User A / User B for fast seeding. They reuse the worker's
 *   sign-in (`signedInA` / `signedInB`), so a test does not hash a password to start.
 * - `seedProject`: create a project owned by A with a single `main.tex` whose
 *   content contains "Introduction" (so the agent stub's search finds it).
 *
 * Specs that aren't testing login get the browser already authenticated as User A (the
 * `page` fixture, from the worker's chain in `session.ts`). Specs that test login use the
 * base test instead (see `flows/auth.spec.ts`).
 */
import { readFile } from "node:fs/promises";

import { test as base, type Page } from "@playwright/test";

import { ApiClient } from "./api";
import { seedRefreshToken } from "./auth";
import { RUN_CONTEXT_FILE, type RunContext } from "./env";
import { readRefreshToken, type SignedIn, WorkerSessions } from "./session";

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
  signedInA: SignedIn;
  signedInB: SignedIn;
  apiA: ApiClient;
  apiB: ApiClient;
  seedProject: (name?: string) => Promise<SeededProject>;
  page: Page;
}

interface WorkerFixtures {
  /** One chain of refresh tokens per user for this worker (see session.ts). */
  sessions: WorkerSessions;
}

export const test = base.extend<Fixtures, WorkerFixtures>({
  sessions: [
    // eslint-disable-next-line no-empty-pattern -- a worker fixture with no dependencies
    async ({}, use) => {
      await use(new WorkerSessions());
    },
    { scope: "worker" },
  ],
  // eslint-disable-next-line no-empty-pattern -- a fixture with no dependencies
  runContext: async ({}, use) => {
    const ctx = JSON.parse(await readFile(RUN_CONTEXT_FILE, "utf-8")) as RunContext;
    await use(ctx);
  },
  signedInA: async ({ sessions, runContext }, use) => {
    await use(await sessions.begin(runContext.userA.email));
  },
  signedInB: async ({ sessions, runContext }, use) => {
    await use(await sessions.begin(runContext.userB.email));
  },
  // The default page starts authenticated as User A, with this test's token from the worker's chain.
  // After the test the token the app holds is kept, so the worker's next test starts from it.
  page: async ({ page, context, sessions, runContext, signedInA }, use) => {
    await seedRefreshToken(context, signedInA.refreshToken);
    await use(page);
    sessions.keep(runContext.userA.email, await readRefreshToken(page));
  },
  apiA: async ({ signedInA }, use) => {
    await use(new ApiClient(undefined, signedInA.accessToken));
  },
  apiB: async ({ signedInB }, use) => {
    await use(new ApiClient(undefined, signedInB.accessToken));
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
