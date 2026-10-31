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

test("the phone editor shows one thing at a time and reaches all four @smoke", async ({
  page,
  seedProject,
}) => {
  const { projectId } = await seedProject();
  await page.goto(`/projects/${projectId}`);

  const nav = page.getByRole("navigation", { name: "Screen" });
  await expect(page.locator(".cm-content")).toBeVisible();

  await nav.getByRole("button", { name: "Preview" }).click();
  await expect(page.locator(".cm-content")).toBeHidden();
  await nav.getByRole("button", { name: "Content" }).click();
  await expect(page.locator(".cm-content")).toBeVisible();

  await page.getByRole("button", { name: /^Switch file/ }).click();
  await expect(page.getByRole("complementary", { name: "Files" })).toBeVisible();
  await page.getByRole("button", { name: /go back to the text/ }).click();
  await expect(page.getByRole("complementary", { name: "Files" })).toBeHidden();

  await nav.getByRole("button", { name: "Agent" }).click();
  await expect(page.getByLabel("Message the agent")).toBeVisible();

  const size = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(size.scrollWidth).toBeLessThanOrEqual(size.innerWidth);
});
