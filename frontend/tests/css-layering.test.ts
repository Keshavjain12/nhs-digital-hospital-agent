/**
 * Guards the cascade-layer structure of globals.css.
 *
 * Regression: bare element styles were written unlayered while Tailwind emits its
 * utilities inside `@layer utilities`. Unlayered CSS beats every layered rule regardless
 * of specificity, so `a { color: nhs-blue }` silently overrode `text-white` on the header
 * brand link, rendering it blue-on-blue and invisible.
 *
 * The failure was invisible to type checking, to lint, and to every component test - the
 * markup was right and the class was applied. Only the rendered page showed it, which is
 * why this asserts on the stylesheet's structure rather than on any component.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/** Comments are stripped: the explanatory comment above quotes the very rule these tests
 *  look for, and would otherwise match as a false positive. Line endings are normalised
 *  so the assertions hold on a CRLF checkout. */
const css = readFileSync(resolve(__dirname, "../app/globals.css"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\r\n/g, "\n");

/** The slice of the file inside `@layer base { ... }`, brace-matched. */
function baseLayer(source: string): string {
  const start = source.indexOf("@layer base {");
  if (start === -1) return "";

  let depth = 0;
  for (let i = source.indexOf("{", start); i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  return "";
}

/** Selectors that open a rule block, e.g. "a" from "  a {". */
function selectorsIn(source: string): string[] {
  return [...source.matchAll(/(?:^|\n)\s*([^{}\n@]+?)\s*\{/g)].map((match) =>
    match[1].trim(),
  );
}

const base = baseLayer(css);
const outsideBase = css.replace(base, "");

describe("globals.css cascade layers", () => {
  it("declares a base layer", () => {
    expect(base).not.toBe("");
  });

  it.each(["a", "body", "html"])(
    "keeps the bare `%s` element style inside @layer base",
    (selector) => {
      // Inside the layer these act as defaults a utility class can override, which is
      // what a base style should do.
      expect(selectorsIn(base)).toContain(selector);
    },
  );

  it.each(["a", "body", "html"])(
    "declares no unlayered bare `%s` rule",
    (selector) => {
      // An unlayered element rule outranks every Tailwind utility. This is the exact
      // shape of the bug.
      expect(selectorsIn(outsideBase)).not.toContain(selector);
    },
  );

  it("keeps :focus-visible unlayered on purpose", () => {
    // The one deliberate exception. It must beat every utility so that no component can
    // ship without a visible focus indicator; moving it into a layer would make it
    // overridable, which is precisely what we do not want here.
    expect(selectorsIn(outsideBase)).toContain(":focus-visible");
  });

  it("orders the base layer before Tailwind's utilities", () => {
    // Layer order decides the winner when specificity ties. Tailwind declares
    // base before utilities; our rules must sit in that base layer, not after it.
    expect(css.indexOf("@layer base {")).toBeGreaterThan(css.indexOf('@import "tailwindcss"'));
  });
});
