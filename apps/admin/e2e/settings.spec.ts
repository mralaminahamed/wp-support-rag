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
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByText(/Settings saved/i)).toBeVisible();
});

test("save profile shows a toast", async ({ page }) => {
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText(/Profile saved/i)).toBeVisible();
});

test("override generation provider shows a toast", async ({ page }) => {
  await expect(page.getByText("Generation", { exact: true })).toBeVisible();
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: /ollama/ }).click();
  await page.getByRole("button", { name: "Save generation" }).click();
  await expect(page.getByText(/Generation set to ollama/i)).toBeVisible();
});

test("embedding width change is rejected with guidance", async ({ page }) => {
  await expect(page.getByText("Embeddings", { exact: true })).toBeVisible();
  // Embedding provider select is the second combobox.
  await page.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: /ollama/ }).click();
  await page.getByRole("button", { name: "Save embedding" }).click();
  await expect(page.getByText(/migration/i).first()).toBeVisible();
});
