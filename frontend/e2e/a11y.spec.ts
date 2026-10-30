/**
 * Every route under axe, WCAG 2.2 AA, in both themes. A screen also has one `main` and one `h1`,
 * which axe reports only as best practices. A known violation goes in `KNOWN_VIOLATIONS`, with its
 * reason; there is none today.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as signedOutTest, type Page } from "@playwright/test";

import { expect, test as signedInTest } from "./support/fixtures";
import { ROUTES } from "./support/routes";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const THEMES = ["light", "dark"] as const;

// A signed-in visitor is redirected away from these, so only a signed-out one can reach the screen.
const SIGNED_OUT_ONLY = new Set(["/login", "/register", "/forgot-password"]);

// Route path → axe rule ids, each entry with a comment giving its reason.
const KNOWN_VIOLATIONS: Record<string, string[]> = {};

async function audit(page: Page, url: string, path: string, theme: (typeof THEMES)[number]) {
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(url);

  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  // The default theme follows the system, so this is what proves the dark run is really dark.
  await expect(page.locator("html")).toHaveClass(theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b)/);

  const { violations } = await new AxeBuilder({ page })
    .withTags(TAGS)
    .disableRules(KNOWN_VIOLATIONS[path] ?? [])
    .analyze();
  const found = violations.map(({ id, nodes }) => `${id}: ${nodes.map((n) => n.target).join(" | ")}`);
  expect(found).toEqual([]);
}

for (const { path, url } of ROUTES) {
  for (const theme of THEMES) {
    const test = SIGNED_OUT_ONLY.has(path) ? signedOutTest : signedInTest;
    test(`route ${path} passes axe in the ${theme} theme @smoke`, async ({ page }) => {
      await audit(page, url, path, theme);
    });
  }
}
