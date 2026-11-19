import { defineConfig } from "@playwright/test";
const modelDemo = process.env.LEARN_WEB_TEST_DEMO === "1";
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: modelDemo
    ? ["models-demo.spec.ts", "ui-demo.spec.ts"]
    : [
        "frontend.spec.ts",
        "ui-enhancements.spec.ts",
        "learning-workflows.spec.ts",
        "resilience.spec.ts",
      ],
  fullyParallel: true,
  workers: 2,
  timeout: 25_000,
  expect: { timeout: 7000 },
  reporter: "list",
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:5174",
    channel: process.env.LEARN_WEB_BROWSER_CHANNEL || "chromium",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: modelDemo
      ? "npm run dev:demo -- --port 5174"
      : "npm run dev -- --port 5174",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
});
