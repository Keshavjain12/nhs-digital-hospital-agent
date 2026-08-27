import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, expect, vi } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";

// Registered manually rather than via vitest-axe/extend-expect, which targets an older
// vitest expect API and fails at runtime here. The matching type augmentation lives in
// types/vitest-axe.d.ts.
expect.extend(axeMatchers);

afterEach(cleanup);

// jsdom implements neither, and both are used by the components under test.
window.HTMLElement.prototype.scrollIntoView = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
