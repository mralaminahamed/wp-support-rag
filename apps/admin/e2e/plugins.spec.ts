// Plugins e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/plugins");
});

test("lists plugins and expands sources", async ({ page }) => {
  await expect(
    page.getByRole("cell", { name: "swift-menu-duplicator", exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "warranty-cart", exact: true }).first(),
  ).toBeVisible();

  // Expand the first row's sources.
  await page.getByRole("button", { name: "Toggle sources" }).first().click();
  await expect(page.getByText("github_readme")).toBeVisible();
});

test("ingest a plugin shows a toast", async ({ page }) => {
  await page.getByRole("button", { name: "Ingest", exact: true }).first().click();
  await expect(page.getByText(/enqueued 7 sources/i)).toBeVisible();
});

test("ingest all shows a toast", async ({ page }) => {
  await page.getByRole("button", { name: "Ingest all" }).click();
  await expect(page.getByText(/Enqueued 10 sources across 2 plugins/i)).toBeVisible();
});

test("register modal submits", async ({ page }) => {
  await page.getByRole("button", { name: "Register plugin" }).click();
  await expect(page.getByRole("heading", { name: "Register plugin" })).toBeVisible();
  await page.getByPlaceholder("my-plugin", { exact: true }).fill("new-plugin");
  await page.getByPlaceholder("My Plugin").fill("New Plugin");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByText(/Registered new-plugin/i)).toBeVisible();
});
