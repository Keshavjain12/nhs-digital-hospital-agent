import { AxeBuilder } from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** Demo credentials. Synthetic accounts on a synthetic dataset; see ASSUMPTIONS.md. */
export const DEMO_PASSWORD = process.env.E2E_PASSWORD ?? "demo-hospital-2026";

export const ACCOUNTS = {
  patient: "patient@example.test",
  doctor: "doctor@example.test",
  nurse: "nurse@example.test",
  admin: "admin@example.test",
} as const;

export type Role = keyof typeof ACCOUNTS;

/**
 * Sign in through the real form.
 *
 * The access token lives in memory only and the refresh token is an httpOnly cookie, so
 * there is no shortcut to inject - which is the design working as intended. Driving the
 * form is also the honest thing to do: it means every authenticated test has exercised the
 * sign-in path a real user takes.
 */
export async function signIn(page: Page, role: Role): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(ACCOUNTS[role]);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();

  try {
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15_000 });
  } catch (error) {
    // The login limiter allows 15 attempts per 15 minutes, and each full run of this suite
    // spends three. Iterating on these tests exhausts it, and the symptom is a bare
    // navigation timeout that looks nothing like its cause - so say so explicitly rather
    // than leaving the next person to work it out. The limiter is in-process, so
    // `docker compose restart api` clears it.
    const rateLimited = await page
      .getByText(/too many attempts/i)
      .isVisible()
      .catch(() => false);

    if (rateLimited) {
      throw new Error(
        `Sign-in for ${role} was rate limited (15 attempts per 15 minutes). ` +
          "This is the limiter working, not a defect. Run `docker compose restart api` " +
          "to clear the in-process counter, or wait for the window to pass.",
      );
    }
    throw error;
  }
}

/**
 * WCAG 2.1 AA, which is what the NHS Service Standard and DTAC require.
 *
 * Restricted to the wcag2a/wcag2aa/wcag21a/wcag21aa tags rather than running everything
 * axe knows: best-practice rules are worth following but failing a build on them
 * misrepresents which findings are conformance failures and which are opinions.
 */
export async function auditPage(page: Page, disableRules: string[] = []) {
  let builder = new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // The Next.js dev-tools overlay is injected into every dev-server page and ships in no
    // build a user ever sees. Auditing it would report failures in someone else's toolbar
    // as failures in this service.
    .exclude("nextjs-portal");
  if (disableRules.length > 0) builder = builder.disableRules(disableRules);
  return builder.analyze();
}

/**
 * True when the element belongs to the application rather than the dev-server overlay.
 *
 * Worth being explicit about: this exclusion exists because the overlay is not part of the
 * product, not because a real failure was inconvenient. Anything inside `nextjs-portal` or
 * carrying Next's own dev-tools markers disappears in `next build`.
 */
export async function isApplicationElement(page: Page, index: number, selector: string) {
  return page.locator(selector).nth(index).evaluate((el) => {
    if (el.closest("nextjs-portal")) return false;
    const id = el.id || "";
    return !(id.startsWith("next-") || el.hasAttribute("data-next-mark"));
  });
}

/** Fails with the rule, the impact and the offending markup, not just a count. */
export function expectNoViolations(results: Awaited<ReturnType<typeof auditPage>>) {
  const detail = results.violations
    .map((v) => {
      const nodes = v.nodes.map((n) => `      ${n.html.slice(0, 160)}`).join("\n");
      return `  [${v.impact}] ${v.id}: ${v.help}\n    ${v.helpUrl}\n${nodes}`;
    })
    .join("\n\n");

  expect(results.violations.length, `\n${detail}\n`).toBe(0);
}

/**
 * Whether the focused element has a visible focus indicator.
 *
 * WCAG 2.4.7. This is the check that cannot be done in jsdom at all: it needs real computed
 * styles from a real layout. A page can have perfect semantics and still be unusable by
 * keyboard if `outline: none` was set somewhere and never replaced.
 */
export async function focusIsVisible(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return false;

    const style = getComputedStyle(el);
    const hasOutline = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0;
    const hasShadow = style.boxShadow !== "none" && style.boxShadow !== "";
    const hasBorderChange = parseFloat(style.borderWidth || "0") > 2;
    return hasOutline || hasShadow || hasBorderChange;
  });
}

/**
 * Tab forwards `count` times, returning a description of each element that took focus.
 *
 * Stops inside the Next.js dev overlay are dropped rather than reported: it sits in the tab
 * order of every dev-server page and in none of the built ones, so counting it would make
 * the tab order look different from the one a user meets.
 */
export async function tabThrough(page: Page, count: number): Promise<string[]> {
  const seen: string[] = [];
  for (let i = 0; i < count; i += 1) {
    await page.keyboard.press("Tab");
    const described = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return "none";
      if (el.closest("nextjs-portal") || el.tagName.toLowerCase() === "nextjs-portal") {
        return "__devtools__";
      }
      const label =
        el.getAttribute("aria-label") ??
        el.textContent?.trim().slice(0, 40) ??
        el.getAttribute("name") ??
        "";
      return `${el.tagName.toLowerCase()}${label ? `:${label}` : ""}`;
    });
    if (described !== "__devtools__") seen.push(described);
  }
  return seen;
}
