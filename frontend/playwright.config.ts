import { defineConfig } from "@playwright/test";

// The app must already be running (make start-replay). Uses the installed Chrome, headless.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:4124",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
  },
});
