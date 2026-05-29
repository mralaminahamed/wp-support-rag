// Dashboard e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("dashboard shows health and metrics", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Health card.
  await expect(page.getByText("Service health")).toBeVisible();
  await expect(page.getByText("development")).toBeVisible();

  // Metric values from the mock.
  await expect(page.getByText("128")).toBeVisible(); // total queries
  await expect(page.getByText("91.0%")).toBeVisible(); // deflection
  await expect(page.getByText("870 ms")).toBeVisible(); // p95

  // Topbar connection badge resolves to healthy.
  await expect(page.getByText("healthy")).toBeVisible();
});

test("sidebar navigates between pages", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Plugins" }).click();
  await expect(page.getByRole("heading", { name: "Plugins" })).toBeVisible();
  await page.getByRole("link", { name: "Playground" }).click();
  await expect(page.getByRole("heading", { name: "Playground" })).toBeVisible();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});
