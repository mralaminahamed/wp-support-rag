// Settings e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/settings");
});

test("generation tab loads with provider select", async ({ page }) => {
  await expect(page.getByText("Generation", { exact: true })).toBeVisible();
  // Provider combobox should exist and show current value
  await expect(page.getByRole("combobox").first()).toBeVisible();
});

test("override generation provider shows a toast", async ({ page }) => {
  await expect(page.getByText("Generation", { exact: true })).toBeVisible();
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: /ollama/i }).click();
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText(/Generation set to ollama/i)).toBeVisible();
});

test("embeddings tab loads with provider select", async ({ page }) => {
  await page.getByRole("link", { name: "Embeddings" }).click();
  await expect(page.getByText("Embeddings", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox").first()).toBeVisible();
});

test("embedding width change is rejected with guidance", async ({ page }) => {
  await page.getByRole("link", { name: "Embeddings" }).click();
  await expect(page.getByText("Embeddings", { exact: true })).toBeVisible();
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: /ollama/i }).click();
  await page.getByRole("button", { name: "Save" }).first().click();
  await expect(page.getByText(/migration/i).first()).toBeVisible();
});
