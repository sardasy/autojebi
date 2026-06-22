import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  use: {
    // docker-compose.override.yml의 frontend 매핑 표준(:3001)을 기본값으로.
    // 호스트 dev 서버(:3000) 사용 시 `E2E_BASE_URL=http://localhost:3000`.
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3001",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-smoke",
      testMatch: /.*(?:program-smoke|notices-flow|notices-search|notices-search-api|ontology-api)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-workflow",
      testMatch: /.*(?:program-search-save|program-bid-workflow|program-spec-hwp|program-admin|real-notice-document-flow)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-ops-live",
      testMatch: /.*program-ops-live\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
