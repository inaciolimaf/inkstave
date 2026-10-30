/** Every route at 390×844 with touch: the page itself must not scroll sideways. */
import { expect, test } from "./support/fixtures";
import { ROUTES } from "./support/routes";

// The editor toolbar needs 461px (measured on the production build). `test.fail` keeps the entry
// honest: the suite goes red the day the editor fits, so the entry cannot outlive the problem.
const KNOWN_OVERFLOW = new Set(["/projects/:projectId"]);

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

for (const { path, url } of ROUTES) {
  test(`route ${path} fits 390x844 @smoke`, async ({ page }) => {
    test.fail(KNOWN_OVERFLOW.has(path), "toolbar overflows on a phone");

    await page.goto(url);
    await expect(page.locator("#root")).not.toBeEmpty();

    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    expect(size.scrollWidth).toBeLessThanOrEqual(size.innerWidth);
  });
}
