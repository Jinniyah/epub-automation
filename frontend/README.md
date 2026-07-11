# frontend/

Not yet scaffolded. This directory is reserved for the React + Vite
project (build-time only -- see `docs/requirements/01-architecture.md`)
and gets its actual `package.json`/`src/`/`dist/` in Epic 7 of
`docs/BACKLOG.md`.

Epic 0 creates this directory as part of matching the project structure
in `docs/requirements/01-architecture.md` §Project structure, without
front-loading frontend scaffolding ahead of its own epic.

## Required: dev-server proxy + Origin rewrite (decide/wire up in Epic 7)

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

**Fix: use Vite's built-in proxy, with the Origin header rewritten to
match Flask's origin**, so the browser only ever talks to one origin
(Vite's) and the proxied request Flask actually receives looks
same-origin too. Do **not** relax `_origin_is_allowed()` itself to fix
this -- that would weaken the same protection in production, since dev
and prod share the same backend code path.

```js
// vite.config.js
export default {
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000", // update to match the dev launcher's actual port
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            // Rewrite Origin to the proxy target so Flask's Origin-vs-host
            // check sees a same-origin request, matching what production
            // (single-origin) traffic looks like.
            proxyReq.setHeader("origin", proxyReq.getHeader("host") as string);
          });
        },
      },
    },
  },
};
```

The API-client facade (Epic 7's own checklist item) should call
relative `/api/...` paths, never an absolute `http://127.0.0.1:<port>`
URL, so this proxy config is the only place that needs to know Flask's
actual port.
