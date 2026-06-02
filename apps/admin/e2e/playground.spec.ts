// Playground e2e. Author: Al Amin Ahamed.
import { expect, test } from "@playwright/test";
import { mockApi } from "./mocks";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/playground");
});

test("sample question click fires query", async ({ page }) => {
  // Greeting examples visible on empty state
  await expect(page.getByText("How do I install the plugin?")).toBeVisible();

  await page.getByRole("checkbox").uncheck(); // disable streaming for mock compat
  await page.getByText("How do I install the plugin?").click();

  // User bubble shows the clicked question
  await expect(page.getByText("How do I install the plugin?")).toBeVisible();
  // Answer arrives
  await expect(page.getByText(/Theme location assignments are not copied/i)).toBeVisible();
});

test("runs a query and submits feedback", async ({ page }) => {
  await page.getByPlaceholder("How do I duplicate a menu?").fill("Does it copy theme locations?");
  // Disable streaming to use the JSON /query endpoint.
  await page.getByRole("checkbox").uncheck();
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText(/Theme location assignments are not copied/i)).toBeVisible();
  const source = page.getByRole("link", { name: /FAQ/ });
  await expect(source).toBeVisible();
  await expect(source).toHaveAttribute(
    "href",
    "https://wordpress.org/plugins/swift-menu-duplicator/#faq",
  );

  await page.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect(page.getByText(/Thanks for the feedback/i)).toBeVisible();
});
