// Playground e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/playground");
});

test("runs a query and submits feedback", async ({ page }) => {
  await page.getByPlaceholder("How do I duplicate a menu?").fill("Does it copy theme locations?");
  // Disable streaming to use the JSON /query endpoint.
  await page.getByRole("checkbox").uncheck();
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText(/Theme location assignments are not copied/i)).toBeVisible();
  await expect(
    page.getByRole("link", { name: /swift-menu-duplicator\/#faq/i }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Yes" }).click();
  await expect(page.getByText(/Thanks for the feedback/i)).toBeVisible();
});
