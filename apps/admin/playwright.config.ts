// Playwright e2e config for the admin app. Author: Al Amin Ahamed.
import { defineConfig, devices } from "@playwright/test";

const PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env["CI"] ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: process.env["E2E_BASE_URL"] ?? `http://localhost:${PORT}`,
    trace: "on-first-retry",
  },
  // Start the Vite dev server for the tests (API is mocked via page.route).
  webServer: {
    command: "pnpm dev",
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env["CI"],
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
