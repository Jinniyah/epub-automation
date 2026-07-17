import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import jsxA11y from "eslint-plugin-jsx-a11y";
import tseslint from "typescript-eslint";

// Assembled by hand (plugins registered explicitly, rules spread from
// each plugin's own recommended config) rather than via `extends`,
// because eslint-plugin-react-hooks@7 / eslint-plugin-jsx-a11y@6's flat
// configs still export their `plugins` key in the legacy array-of-
// strings shorthand, which ESLint 9's flat-config loader rejects when
// spread directly into `extends`.
export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...reactHooks.configs["recommended-latest"].rules,
      ...reactRefresh.configs.vite.rules,
      // 03-gui-ux-design.md's "fully-clickable row" pattern uses real
      // <button>/<label> elements, not clickable <div>s -- jsx-a11y's
      // recommended rules are the CI-enforced backstop for that, per
      // 09-testing-strategy.md's accessibility-testing section.
      ...jsxA11y.flatConfigs.recommended.rules,
      // Enforces the single-stylesheet rule (docs/requirements/
      // 03-gui-ux-design.md §Visual design system, docs/BACKLOG.md
      // Epic 8.6): every class/token lives in frontend/src/index.css,
      // never an inline `style` prop. Uses core ESLint's
      // `no-restricted-syntax` (an AST selector, not a JSX-specific
      // rule) rather than `eslint-plugin-react`'s `forbid-dom-props`,
      // since that plugin isn't otherwise a dependency of this project
      // and this project's toolchain otherwise favors already-present
      // plugins (see this file's own header comment) over adding a new
      // one just for a single rule.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='style']",
          message:
            "No inline `style` props -- add a class to frontend/src/index.css instead (docs/requirements/03-gui-ux-design.md §Visual design system: exactly one stylesheet).",
        },
      ],
    },
  },
);
