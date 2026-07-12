import "@testing-library/jest-dom/vitest";
import { expect } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";

// axe-core assertions in component tests (09-testing-strategy.md
// §Accessibility testing) -- `expect(container).toHaveNoViolations()`.
expect.extend(axeMatchers);
