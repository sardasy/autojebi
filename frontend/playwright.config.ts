import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  // 실제 Claude/G2B 호출이 걸린 단계(analyze·grade·문서분석·규격추출)는 수십 초가
  // 걸릴 수 있어 기본 5초 expect/30초 test 타임아웃으로는 토스트 대기가 불안정하다.
  timeout: 180_000,
  expect: { timeout: 30_000 },
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
      testMatch: /.*(?:program-search-save|program-bid-workflow|program-spec-hwp|program-hwp-field-mapping|program-admin|real-notice-document-flow)\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-ops-live",
      testMatch: /.*program-ops-live\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
