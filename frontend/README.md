# frontend/

React 19 + TypeScript, built with Vite. Scaffolded and built out in
Epic 7/8 of `docs/BACKLOG.md` — see `CODEBASE_INDEX.md`'s Epic 7+8
session notes for the full account of what changed from the stock
`create-vite` template and why.

Build-time only, per `docs/requirements/01-architecture.md` — the
packaged `.exe` bundles the compiled static output in `dist/`, never
Node/npm itself.

## Toolchain notes

- **ESLint, not oxlint.** `create-vite`'s current template ships
  oxlint by default; swapped for ESLint 9 (flat config,
  `eslint.config.js`) specifically to get `eslint-plugin-jsx-a11y`
  wired in (`09-testing-strategy.md` §Accessibility testing requires
  it) — oxlint doesn't have an equivalent yet.
- **`eslint-plugin-react-hooks` is pinned to the classic 5.x line**,
  not the newer 7.x default `npm install` would otherwise pick up.
  7.x's additional rules (`set-state-in-effect`,
  `immutability`, etc.) assume the React Compiler, which this project
  doesn't use (see the vanilla `React Compiler` section below) — several
  of those rules actively fight legitimate hand-written patterns this
  codebase relies on (e.g. `usePollingStatus()`'s recursive
  `setTimeout` polling loop).
- **`vitest-axe`'s shipped types needed a local patch**
  (`src/test/vitest-axe.d.ts`) — its own `.d.ts` targets an older `Vi.
  Assertion` global-namespace convention that vitest 4.x's
  `@vitest/expect` no longer reads; the augmentation there retargets
  the same matcher to the `declare module "vitest"` extension point
  `@testing-library/jest-dom/vitest` already uses.
- **React Compiler is not enabled** — same call the stock template
  defaults to (dev/build performance cost), and this codebase leans on
  hand-written hooks (see above) that predate it.

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Vite dev server on `:5173`, proxying `/api` to the Flask backend (see below) |
| `npm run build` | `tsc -b && vite build` — production static output to `dist/` |
| `npm run lint` | ESLint (incl. `eslint-plugin-jsx-a11y`) |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm test` | Vitest, one run |
| `npm run coverage` | Vitest with the 80% coverage floor enforced (`vite.config.ts`) |

## Dev-server proxy + Origin rewrite (implemented, Epic 7)

`backend/app.py::_origin_is_allowed()` rejects any mutating request
(`POST`/`PUT`/`DELETE`/`PATCH`) whose `Origin` header doesn't match the
address the request actually arrived on (ADR-0008's CSRF/DNS-rebinding
guard, added in the Epic 6 post-review fixes). That's correct and
required in production, where the built React `dist/` is served from the
same origin as the Flask API.

During development, Vite's dev server runs on its own port
(`localhost:5173` by default), separate from Flask/waitress's
dynamically-assigned port (`launcher.py::find_free_port()`) -- a raw
`fetch("http://127.0.0.1:<port>/api/...")` from Vite-served pages would
be a genuine cross-origin request and get `403`'d by design, not by bug.

**Fix (implemented in `vite.config.ts`): Vite's built-in proxy, with the
Origin header rewritten to match Flask's origin**, so the browser only
ever talks to one origin (Vite's) and the proxied request Flask actually
receives looks same-origin too. `_origin_is_allowed()` itself was never
relaxed -- dev and prod share the same backend code path.

```ts
// vite.config.ts (actual, not illustrative)
const BACKEND_DEV_PORT = 5000; // update to match the dev backend's actual port

export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${BACKEND_DEV_PORT}`,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("origin", `http://127.0.0.1:${BACKEND_DEV_PORT}`);
          });
        },
      },
    },
  },
});
```

`src/api/client.ts` (the API-client facade) calls relative `/api/...`
paths only, never an absolute `http://127.0.0.1:<port>` URL, so this
proxy config is the only place that needs to know the backend's actual
dev-time port. `launcher.py`'s production path assigns a port
dynamically; for local frontend dev, run the backend on
`BACKEND_DEV_PORT` (or update the constant to match).

## Directory layout

```
src/
├── api/           # client.ts (fetch facade), types.ts (wire-contract types)
├── hooks/         # usePollingStatus, useFocusTrap, useAriaLiveThrottled
├── components/
│   └── shared/    # BigButton, RadioRow, ToggleSwitch, EditableFieldRow,
│                  # Overlay, FieldCorrectionPopup, VoicePicker, LiveRegion
├── viewmodels/    # useVoiceAssignmentView, useWorkingScreenView
├── screens/       # one file per screen, 03-gui-ux-design.md's encounter order
├── utils/         # authorName.ts (Last, First <-> author_first/author_last)
└── App.tsx        # top-level container: onboarding phase + main polling loop
```

Every `.tsx`/`.ts` file with meaningful logic has a co-located
`*.test.tsx`/`*.test.ts` — see `CODEBASE_INDEX.md` for current test
counts and coverage.
