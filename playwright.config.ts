import { defineConfig } from "@playwright/test";

export const STATE = "tests/e2e/.state";
export const WEBHOOK = "http://127.0.0.1:8090";

export default defineConfig({
  testDir: "tests/e2e",
  // Every test rewrites the one settings file the server reads.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:8099",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
  webServer: [
    {
      command: "uv run python tests/mock_webhook.py --port 8090",
      url: `${WEBHOOK}/posts`,
      reuseExistingServer: !process.env.CI,
    },
    {
      command:
        `rm -rf ${STATE} && mkdir -p ${STATE} && cp tests/e2e/fixtures/chats.json ${STATE}/chats.json && ` +
        `exec uv run qq-notify-forward serve --settings ${STATE}/settings.json --chats ${STATE}/chats.json --port 8099`,
      url: "http://127.0.0.1:8099/api/state",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
