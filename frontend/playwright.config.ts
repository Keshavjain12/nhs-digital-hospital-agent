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
  // Serial, for a reason worth stating rather than tuning away.
  //
  // Refresh tokens rotate, and replaying a rotated one revokes *every* session for that
  // user - not just that chain (app/services/auth.py). A legitimate replay and a stolen
  // token are indistinguishable, so ending all of them is the only safe response, and that
  // is the right call.
  //
  // The demo dataset has one account per role. Running both spec files across three engines
  // put six browser contexts on patient@example.test, all rotating their own tokens; one
  // replay signed all the others out mid-test, and the failure surfaced as "the Start button
  // is missing" on a page that had silently become the sign-in screen.
  //
  // The fix is not to weaken the control or to widen a timeout. It is to stop pretending one
  // person is six, so files run one at a time.
  fullyParallel: false,
  workers: 1,
  // Generous: a first authenticated round trip against a cold API is slow, and a tight bound
  // reports contention as a defect.
  timeout: 90_000,
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
