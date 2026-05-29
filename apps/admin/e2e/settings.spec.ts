// Settings e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/settings");
});

test("test connection reports healthy", async ({ page }) => {
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText(/service healthy/i)).toBeVisible();
});

test("save settings shows a toast", async ({ page }) => {
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Settings saved/i)).toBeVisible();
});
