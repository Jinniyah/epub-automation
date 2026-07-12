/* eslint-disable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars */
// vitest-axe@0.1.0 ships its `Assertion` augmentation for an older
// `Vi.Assertion` global-namespace convention that newer vitest
// (@vitest/expect's `declare module "vitest" { interface Matchers }`
// extension point, the same one @testing-library/jest-dom/vitest uses)
// no longer picks up. This is the same augmentation, retargeted -- the
// empty extending interfaces below are the standard TS declaration-
// merging idiom for this (identical shape to jest-dom's own shipped
// vitest.d.ts), not actually empty/redundant.
import type { AxeResults } from "axe-core";

interface AxeMatchers<T = unknown> {
  toHaveNoViolations(): { message(): string; pass: boolean };
}

declare module "vitest" {
  interface Assertion<T = AxeResults> extends AxeMatchers<T> {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
