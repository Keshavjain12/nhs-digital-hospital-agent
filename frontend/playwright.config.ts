import { defineConfig, devices } from "@playwright/test";

/**
 * Browser-driven tests: the accessibility audit and the cross-browser pass.
 *
 * These are deliberately separate from the Vitest suite. Vitest renders components into
 * jsdom, which is fast and right for component behaviour but cannot answer the questions
 * this project actually needs answered - whether focus is *visible*, whether contrast
 * computes to 4.5:1 against what is really painted, whether the layout survives 200% zoom.
 * jsdom has no layout engine and no rendering, so it cannot see any of that.
 *
 * Both servers must already be running (docker compose up, npm run dev). There is no
 * webServer block on purpose: starting the API from here would hide which of the two is
 * broken when something fails.
 */
export default defineConfig({
  testDir: "./e2e",
  // Accessibility failures are not flaky, and retrying them would mask a real intermittent
  // problem rather than fix it.
  retries: 0,
  fullyParallel: true,
  // Three engines at full parallelism on one developer machine starved each other: a page
  // that audits in 2.5s alone took 32s and tripped the timeout. The failure was contention,
  // not a violation, and a suite that reports infrastructure noise as accessibility
  // findings is worse than no suite.
  workers: 4,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    // WebKit is the engine behind Safari, and the closest thing to iOS Safari that can be
    // run on Windows. It is not Safari, and §5 of the cross-browser report says so.
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
