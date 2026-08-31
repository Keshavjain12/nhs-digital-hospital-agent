import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import {
  API_BASE,
  auditPage,
  expectNoViolations,
  focusIsVisible,
  isApplicationElement,
  signIn,
  tabThrough,
  type Role,
} from "./support";

/**
 * WCAG 2.1 AA audit against a real browser.
 *
 * Automated tooling finds roughly a third of accessibility problems. Everything here
 * passing means the machine-detectable failures are absent - not that the service is
 * accessible. The judgement-based checks (does the emergency banner make sense when heard
 * rather than seen, is the focus order logical rather than merely present) still need a
 * person, and docs/testing/accessibility-audit.md records which of those have not been done.
 *
 * ---
 *
 * On why the authenticated tests share one session per role rather than signing in each
 * time: the first version signed in per test, and every authenticated test failed with a
 * 429. That was the login rate limiter doing its job - fourteen sign-ins in a few seconds
 * from one address is what it exists to stop.
 *
 * Playwright's usual answer is to save storageState and reuse it across workers, but that
 * does not work here either, and for a more interesting reason: the refresh token rotates
 * on every use and presenting a rotated one revokes the entire chain. Several parallel
 * workers replaying one saved cookie is precisely the reuse pattern the auth design treats
 * as a stolen token. So each role signs in exactly once and runs its tests in that one
 * context, serially.
 */

// --- Pages a patient reaches before signing in -------------------------------------

const PUBLIC_PAGES = [
  { path: "/", name: "home" },
  { path: "/login", name: "sign in" },
  { path: "/register", name: "register" },
  { path: "/forgot-password", name: "forgot password" },
  { path: "/not-authorised", name: "not authorised" },
];

test.describe("public pages", () => {
  for (const target of PUBLIC_PAGES) {
    test(`${target.name} has no WCAG 2.1 AA violations`, async ({ page }) => {
      await page.goto(target.path);
      expectNoViolations(await auditPage(page));
    });
  }

  test("every interactive element on the sign-in page shows a visible focus ring", async ({
    page,
  }) => {
    // WCAG 2.4.7. The project sets :focus-visible deliberately outside any cascade layer,
    // because unlayered CSS beats all layered CSS regardless of specificity. This proves
    // that decision still holds after every later change to the stylesheet.
    await page.goto("/login");

    const focusable = page.locator("a[href], button, input, select, textarea, summary");
    const count = await focusable.count();
    expect(count).toBeGreaterThan(3);

    const selector = "a[href], button, input, select, textarea, summary";
    const invisible: string[] = [];
    for (let i = 0; i < count; i += 1) {
      const element = focusable.nth(i);
      if (!(await element.isVisible())) continue;
      // The dev-server overlay injects its own button, which has no focus ring and is in
      // no build a user ever loads. Skipped as not-our-markup, not as an accepted failure.
      if (!(await isApplicationElement(page, i, selector))) continue;
      await element.focus();
      if (!(await focusIsVisible(page))) {
        invisible.push((await element.evaluate((el) => el.outerHTML)).slice(0, 120));
      }
    }

    expect(invisible, `no visible focus indicator on:\n${invisible.join("\n")}`).toHaveLength(0);
  });

  test("the html element declares a language", async ({ page }) => {
    // WCAG 3.1.1. Without it a screen reader reads the page with whatever voice it last
    // used, which for a Welsh speaker is the difference between usable and not.
    await page.goto("/");
    expect(await page.getAttribute("html", "lang")).toBeTruthy();
  });
});

// --- One signed-in session per role ------------------------------------------------

/** Opens a single context for `role`, signs in once, and hands the same page to each test. */
function describeSignedIn(role: Role, title: string, body: (getPage: () => Page) => void) {
  test.describe.serial(title, () => {
    let context: BrowserContext;
    let page: Page;

    test.beforeAll(async ({ browser }) => {
      // An explicit context, not browser.newPage(): axe-core/playwright refuses to run
      // against a page created on the default context.
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

describeSignedIn("patient", "patient pages", (getPage) => {
  const PAGES = [
    { path: "/dashboard", name: "patient dashboard" },
    { path: "/appointments", name: "appointments" },
    { path: "/appointments/book", name: "booking" },
    { path: "/symptom-check", name: "symptom check" },
  ];

  for (const target of PAGES) {
    test(`${target.name} has no WCAG 2.1 AA violations`, async () => {
      const page = getPage();
      await page.goto(target.path);
      // Data-driven pages render a loading state first; auditing that audits a spinner.
      await page.waitForLoadState("networkidle");
      expectNoViolations(await auditPage(page));
    });
  }

  test("every page has exactly one h1 and a document title", async () => {
    const page = getPage();
    for (const path of ["/dashboard", "/appointments", "/symptom-check"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const h1Count = await page.locator("h1").count();
      expect(h1Count, `${path} has ${h1Count} h1 elements`).toBe(1);
      expect((await page.title()).length, `${path} has an empty title`).toBeGreaterThan(0);
    }
  });

  test("the symptom check can be started and answered by keyboard alone", async () => {
    // Known defect WEBKIT-SESSION: WebKit stops storing the rotated refresh cookie after
    // the second page load, so the third replays a spent token, the server correctly
    // reads that as reuse, and every session for the user is revoked. Not a defect in
    // this test. See docs/testing/cross-browser.md.
    test.fixme(
      test.info().project.name === "webkit",
      "WEBKIT-SESSION: rotated refresh cookie not stored; see docs/testing/cross-browser.md",
    );

    // The longest test here: it restarts a conversation, waits for the server, and tabs
    // through the page. WebKit runs it slowest and was hitting the default limit.
    test.setTimeout(90_000);

    const page = getPage();
    await page.goto("/symptom-check");
    // Waiting for a control rather than networkidle - the chat page keeps requests in
    // flight, and Firefox never reported idle at all.
    // Generous, because this waits on a first authenticated round trip: with three engines
    // running at once against a cold API the query can take far longer than it does alone,
    // and a tight bound here reports contention as a defect.
    await expect(
      page.getByRole("button", { name: /start again|^start$/i }).first(),
    ).toBeVisible({ timeout: 40_000 });

    // The skip link must exist so a keyboard user is not dragged through the whole header
    // on every page.
    await expect(page.getByRole("link", { name: /skip to main content/i })).toBeAttached();

    // Its position in the tab order is only assertable where links are tabbable by default.
    // WebKit leaves anchors out of the tab sequence unless the reader has turned on Safari's
    // Full Keyboard Access, so on WebKit the first stop is the language select - which is
    // Safari behaving as Safari, not a defect here. Recorded in the cross-browser report.
    if (test.info().project.name !== "webkit") {
      const firstStops = await tabThrough(page, 4);
      expect(
        firstStops[0]?.toLowerCase().includes("skip to main content"),
        `first application tab stop was ${firstStops[0]}, not the skip link`,
      ).toBe(true);
    }

    // The page has three legitimate states: no check under way (a Start button), one in
    // progress (an answer box), and one that has ended with no input at all - which is
    // correct when the patient has just been told to call 999. Which state the demo account
    // is in depends on what ran before, so drive it into a known one rather than assume.
    //
    // "Start again" is present in every state, so it is the reliable route to a fresh,
    // answerable conversation.
    const startAgain = page.getByRole("button", { name: /start again/i });
    if (await startAgain.isVisible().catch(() => false)) {
      await startAgain.focus();
      await page.keyboard.press("Enter");
      // A conversation in progress asks for confirmation; a closed one restarts at once.
      const confirm = page.getByRole("dialog").getByRole("button", { name: /start again/i });
      if (await confirm.isVisible().catch(() => false)) await confirm.click();
    } else {
      await page.getByRole("button", { name: /^start$/i }).focus();
      await page.keyboard.press("Enter");
    }

    // Waiting for the answer box rather than for networkidle: the chat page keeps requests
    // in flight and Firefox never reached idle, timing the test out at a minute.
    // By role, not by input[type=text]: the field carries no type attribute (text is the
    // default), so an attribute selector misses it entirely. The role is also what assistive
    // technology actually goes on.
    const answer = page.getByRole("textbox").first();
    await expect(answer).toBeVisible({ timeout: 20_000 });

    // Reachable by keyboard, and actually usable once reached.
    await answer.focus();
    expect(await focusIsVisible(page)).toBe(true);
    await page.keyboard.type("headache");
    await expect(answer).toHaveValue("headache");
  });

  test("the cancel dialog traps focus, closes on Escape, and returns focus", async () => {
    const page = getPage();
    await page.goto("/appointments");
    await page.waitForLoadState("networkidle");

    const trigger = page.getByRole("button", { name: /cancel this appointment/i }).first();
    if ((await trigger.count()) === 0) {
      test.skip(true, "no cancellable appointment in the seeded data");
      return;
    }

    await trigger.focus();
    await trigger.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    // A native <dialog> opened with showModal() makes the rest of the page inert, which is
    // what makes the focus trap real rather than something reimplemented in JavaScript.
    const focusInside = await page.evaluate(() => {
      const open = document.querySelector("dialog[open]");
      return open ? open.contains(document.activeElement) : false;
    });
    expect(focusInside).toBe(true);

    expectNoViolations(await auditPage(page));

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();

    // Returning focus to the trigger is what stops a keyboard user being dumped at the top
    // of the document every time they dismiss something.
    const returned = await page.evaluate(
      () => document.activeElement?.textContent?.toLowerCase().includes("cancel") ?? false,
    );
    expect(returned).toBe(true);
  });

  test("patient pages reflow at 320px without horizontal scrolling", async () => {
    // WCAG 1.4.10. 320px is the criterion's own threshold - equivalent to 400% zoom on a
    // 1280px screen, and roughly the narrowest phone still in use.
    const page = getPage();
    await page.setViewportSize({ width: 320, height: 800 });

    try {
      for (const path of ["/dashboard", "/appointments", "/symptom-check"]) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");

        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${path} scrolls sideways by ${overflow}px at 320px`).toBeLessThanOrEqual(
          1,
        );
      }
    } finally {
      // The session is shared with the tests that follow, so the viewport must be put back.
      await page.setViewportSize({ width: 1280, height: 720 });
    }
  });
});

describeSignedIn("doctor", "clinical pages", (getPage) => {
  const PAGES = [
    { path: "/staff/queue", name: "clinical queue" },
    { path: "/staff/triage", name: "triage review" },
  ];

  for (const target of PAGES) {
    test(`${target.name} has no WCAG 2.1 AA violations`, async () => {
      const page = getPage();
      await page.goto(target.path);
      await page.waitForLoadState("networkidle");
      expectNoViolations(await auditPage(page));
    });
  }

  test("the clinical queue stays usable at 200% zoom", async () => {
    // A wide data table is the hardest case for reflow and the one a clinician uses most.
    const page = getPage();
    await page.setViewportSize({ width: 640, height: 720 });

    try {
      await page.goto("/staff/queue");
      await page.waitForLoadState("networkidle");

      // A table scrolling inside its own container is fine; the page body scrolling
      // sideways is not, because it moves the whole layout out from under the reader.
      const overflow = await page.evaluate(
        () => document.body.scrollWidth - document.body.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    } finally {
      await page.setViewportSize({ width: 1280, height: 720 });
    }
  });
});

describeSignedIn("admin", "administrative pages", (getPage) => {
  const PAGES = [
    { path: "/admin/dashboard", name: "admin dashboard" },
    { path: "/admin/audit", name: "audit trail" },
    { path: "/admin/models", name: "model monitoring" },
  ];

  for (const target of PAGES) {
    test(`${target.name} has no WCAG 2.1 AA violations`, async () => {
      const page = getPage();
      await page.goto(target.path);
      await page.waitForLoadState("networkidle");
      expectNoViolations(await auditPage(page));
    });
  }
});
