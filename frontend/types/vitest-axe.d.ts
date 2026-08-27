/**
 * Type augmentation for the axe matchers registered in tests/setup.ts.
 *
 * Vitest 4 renamed the augmentation target from `Assertion` to `Matchers`, and
 * vitest-axe still ships the older declaration - so its matchers work at runtime while
 * tsc reports them as missing. Declaring the one matcher we use is more honest than
 * loosening the compiler for the whole test suite.
 */

import type { AxeResults } from "axe-core";

declare module "vitest" {
  interface Matchers<T = unknown> {
    toHaveNoViolations: () => T;
  }
}

export type { AxeResults };
