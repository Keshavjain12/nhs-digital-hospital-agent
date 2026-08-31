import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { API_BASE, signIn } from "./support";

/**
 * Cross-browser checks: the things that differ between engines rather than the things that
 * differ between pages.
 *
 * The accessibility suite already runs on all three engines, so rule-level conformance is
 * covered there. This covers what is left: whether the core journeys actually complete,
 * whether the platform features this project leans on behave the same everywhere, and
 * whether the layout holds on a phone.
 *
 * Runs against Chromium, Firefox and WebKit. WebKit is the engine behind Safari and the
 * closest thing to it available on Windows - it is not Safari, and the report says so.
 */

function describeSignedIn(role: "patient" | "doctor", title: string, body: (p: () => Page) => void) {
  test.describe.serial(title, () => {
    let context: BrowserContext;
    let page: Page;

    test.beforeAll(async ({ browser }) => {
      context = await browser.newContext();
      page = await context.newPage();
      await signIn(page, role);
    });

    test.afterAll(async () => {
      // Sign out on the server, not just close the browser. Closing a context abandons the
      // session rather than ending it, so each role accumulated live sessions across the
      // run - and when any one of them tripped reuse detection, revoke_all_for_user took
      // out the session the next test was relying on. The symptom was a test failing
      // because a page had quietly become the sign-in screen.
      await context?.request.post(`${API_BASE}/auth/logout`).catch(() => {});
      await context?.close();
    });

    body(() => page);
  });
}

// --- Platform features this project depends on -------------------------------------

test("the native dialog element is supported", async ({ page }) => {
  // The cancel confirmation is a native <dialog> opened with showModal(), chosen because it
  // gives a real focus trap and page inertness rather than a JavaScript approximation. If
  // an engine lacked it the confirmation would silently not be modal, which is exactly the
  // kind of failure that does not announce itself.
  await page.goto("/login");

  const supported = await page.evaluate(() => {
    const el = document.createElement("dialog");
    return typeof el.showModal === "function" && typeof el.close === "function";
  });

  expect(supported).toBe(true);
});

test("Intl formats dates consistently for en-GB", async ({ page }) => {
  // Appointment times are formatted client-side. An engine that fell back to US ordering
  // would show 3 April as 4 March - wrong, plausible-looking, and about an appointment.
  await page.goto("/login");

  const formatted = await page.evaluate(() =>
    new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" }).format(
      new Date(Date.UTC(2026, 3, 3)),
    ),
  );

  expect(formatted).toBe("3 April 2026");
});

// --- The journeys a patient actually makes -----------------------------------------

describeSignedIn("patient", "patient journeys", (getPage) => {
  test("the dashboard renders its own content, not an error state", async () => {
    const page = getPage();
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // A page that renders its shell but fails every request still looks fine in a
    // screenshot, so assert the absence of the failure state explicitly.
    await expect(page.getByText(/could not reach the service/i)).toHaveCount(0);
  });

  test("appointments load and show a booking reference", async () => {
    // Known defect WEBKIT-SESSION: WebKit stops storing the rotated refresh cookie after
    // the second page load, so the third replays a spent token, the server correctly
    // reads that as reuse, and every session for the user is revoked. Not a defect in
    // this test. See docs/testing/cross-browser.md.
    test.fixme(
      test.info().project.name === "webkit",
      "WEBKIT-SESSION: rotated refresh cookie not stored; see docs/testing/cross-browser.md",
    );

    const page = getPage();
    await page.goto("/appointments");

    // Include past appointments before asserting. The seeded slots are generated relative
    // to seed time, so a database seeded a while ago has no *upcoming* bookings at all and
    // the page correctly says "No appointments" - which would fail this check for a reason
    // that has nothing to do with the browser. What is being tested is that real
    // appointment data reaches the page, so ask for all of it.
    await page.getByRole("checkbox", { name: /include past and cancelled/i }).check();

    // References are APT-YYYY-NNNNNN. The bound is generous because WebKit is consistently
    // the slowest of the three and a tight one reports engine speed as a defect.
    await expect(page.getByText(/APT-\d{4}-\d+/).first()).toBeVisible({ timeout: 45_000 });
  });

  test("the booking page offers slots", async () => {
    const page = getPage();
    await page.goto("/appointments/book");

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText(/could not reach the service/i)).toHaveCount(0);
  });

  test("the layout holds at a 360px phone viewport", async () => {
    // 360px is the most common Android width. Distinct from the 320px reflow check in the
    // accessibility suite: that one is a WCAG threshold, this is the real-world case.
    const page = getPage();
    await page.setViewportSize({ width: 360, height: 740 });

    try {
      for (const path of ["/dashboard", "/appointments", "/symptom-check"]) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${path} scrolls sideways by ${overflow}px at 360px`).toBeLessThanOrEqual(
          1,
        );
      }
    } finally {
      await page.setViewportSize({ width: 1280, height: 720 });
    }
  });
});

// --- The clinical view -------------------------------------------------------------

describeSignedIn("doctor", "clinical journeys", (getPage) => {
  test("the queue renders rows", async () => {
    const page = getPage();
    await page.goto("/staff/queue");

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("table").or(page.getByRole("list")).first()).toBeVisible({
      timeout: 20_000,
    });
  });

  test("the triage view loads without a client-side error", async () => {
    const page = getPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    await page.goto("/staff/triage");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // An uncaught exception in one engine and not another is the classic cross-browser
    // failure, and it does not necessarily change what the page looks like.
    expect(errors, `uncaught page errors:\n${errors.join("\n")}`).toHaveLength(0);
  });
});
