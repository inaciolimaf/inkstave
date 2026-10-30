/** Smoke of every route: a page opens signed in, with fake ids, without crashing. */
import { expect, test } from "./support/fixtures";
import { ROUTES } from "./support/routes";

for (const { path, url } of ROUTES) {
  test(`route ${path} opens @smoke`, async ({ page }) => {
    const crashes: string[] = [];
    page.on("pageerror", (error) => crashes.push(error.message));

    await page.goto(url);

    await expect(page.locator("#root")).not.toBeEmpty();
    await expect(page.getByText("Unexpected Application Error")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Try again" })).toHaveCount(0);
    expect(crashes).toEqual([]);
  });
}
