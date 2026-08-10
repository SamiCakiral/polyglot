import { defineConfig } from "@playwright/test";

const mockBaseUrl = "http://127.0.0.1:4175";

export default defineConfig({
  testDir: "./tests/e2e/shell",
  outputDir: "./test-results/w17-shell",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "list",
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: mockBaseUrl,
    colorScheme: "light",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 4175 --strictPort",
      url: mockBaseUrl,
      env: { VITE_ENABLE_API_MOCKS: "true" },
      reuseExistingServer: false,
      stderr: "ignore",
      stdout: "ignore",
      timeout: 30_000,
    },
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 4176 --strictPort",
      url: "http://127.0.0.1:4176",
      env: { VITE_ENABLE_API_MOCKS: "" },
      reuseExistingServer: false,
      stderr: "ignore",
      stdout: "ignore",
      timeout: 30_000,
    },
  ],
  projects: [
    { name: "shell-320", use: { viewport: { width: 320, height: 720 } } },
    { name: "shell-768", use: { viewport: { width: 768, height: 900 } } },
    { name: "shell-1440", use: { viewport: { width: 1440, height: 900 } } },
    {
      name: "zoom-200",
      metadata: { physicalViewportWidth: 1440, zoomPercent: 200 },
      use: { viewport: { width: 720, height: 450 } },
    },
  ],
});
