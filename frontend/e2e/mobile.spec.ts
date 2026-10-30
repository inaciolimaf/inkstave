/** Every route at 390×844 with touch: the page itself must not scroll sideways. */
import { expect, test } from "./support/fixtures";
import { ROUTES } from "./support/routes";

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

for (const { path, url } of ROUTES) {
  test(`route ${path} fits 390x844 @smoke`, async ({ page }) => {
    await page.goto(url);
    await expect(page.locator("#root")).not.toBeEmpty();

    const size = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    expect(size.scrollWidth).toBeLessThanOrEqual(size.innerWidth);
  });
}
