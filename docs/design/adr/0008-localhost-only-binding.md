# ADR-0008: Flask/waitress binds to `127.0.0.1` only — hard requirement, not a default

## Status
Accepted

## Context
The Flask API (ADR-0001) has no authentication layer of any kind, and it
can pop native file dialogs and read/write arbitrary paths on the host
filesystem on request. This was previously only an implicit assumption
("single-user, localhost-bound" mentioned in passing in
`docs/requirements/00-overview-and-goals.md` and
`docs/requirements/08-open-questions-and-assumptions.md`) rather than
something the code itself enforced. An accidental `0.0.0.0` bind — even
a temporary one made for local debugging convenience and never reverted
— would expose this unauthenticated, filesystem-capable surface to
anything else on the same home network: other devices, a compromised
IoT device, or a neighbor within wifi range, not just her own browser.

## Decision
`waitress.serve(app, host="127.0.0.1", port=...)` — the host argument is
a **fixed constant** in `launcher.py`, never a configurable setting,
environment variable, or CLI flag. This is promoted from an implicit
assumption to an explicit, code-enforced requirement.

## Consequences
- Removes an entire class of risk (network-exposed, unauthenticated,
  filesystem-capable API) by construction, rather than relying on
  operator discipline to never bind more broadly.
- If multi-device/networked access is ever wanted in a future version
  (e.g. reaching the GUI from a phone on the same home network), that
  requires a genuine new design pass with a real authentication story
  first — it is explicitly **not** a one-line change to the bind
  address, and this ADR should be revisited (superseded, not silently
  bypassed) if that need arises.
- This requirement is what makes the native-folder-picker approach
  (ADR-0006) and the single-instance/per-machine model (ADR-0007) safe
  assumptions to build on — both already assumed single-machine,
  single-user use; this decision is what makes the code itself enforce
  that assumption rather than leaving it as an unstated precondition.
- Port selection can still be dynamic (find a free local port
  automatically) — only the host/interface is fixed, not the port.

## Alternatives Considered
- **Leave the bind address configurable, document `127.0.0.1` as the
  recommended default** — rejected: a documented recommendation is not
  a guarantee, and the cost of getting this wrong (an unauthenticated,
  filesystem-capable API exposed to a home network) is severe enough
  relative to the near-zero cost of hardcoding it that no configurability
  is worth preserving here.
- **Add lightweight authentication (e.g. a local token) instead of
  restricting the bind address** — rejected as unnecessary complexity
  for this version: the localhost-only bind already fully addresses the
  threat model for a single-machine, single-user tool; token auth would
  only matter if networked access were also being added, which is
  explicitly out of scope.

## Update (Epic 6, 2026-07-10): Origin-header check added

A gap in the threat model above, found during a post-Epic-6 security
review: "no authentication needed, localhost-only bind fully addresses
the threat model" was true for the threat this ADR was written against
— *other devices* reaching the API over the network. It understated a
different threat still inside the localhost-only boundary: a malicious
or compromised **webpage open in another browser tab on her own
machine** can still send this server a request. Browsers only block
that page's JavaScript from *reading* a cross-origin response — they
don't stop the request from being *sent and acted on* in the first
place, for request shapes that don't require a CORS preflight
(`multipart/form-data`, or a body-less `POST`). Concretely, this made
`POST /api/quit` (kills the server) and the file-upload route reachable
from any webpage she happened to have open, with zero interaction from
her.

**Decision (unchanged in spirit, refined in scope):** every mutating
request (`POST`/`PUT`/`DELETE`/`PATCH`) is now rejected with `403`
unless its `Origin` header — when the browser sends one at all — equals
`http://{request.host}`, i.e. the address the request actually arrived
on (`backend/app.py::_origin_is_allowed()`, wired via a single
`before_request` hook). Non-browser clients (curl, the CLI) never send
`Origin` and are unaffected.

**Why this isn't the "lightweight authentication" option already
rejected above:** that alternative meant a shared secret/token guarding
against *networked* access — real auth, with real complexity (issuing,
storing, and checking a credential). An Origin check requires no secret
at all; it can't be forged by a normal browser (which is the entire
class of attacker this closes), and it does nothing against a genuinely
malicious *local* process already running with her privileges — which
was never in scope for this ADR either. It's the narrowest possible fix
for the specific gap found, not a reopening of the auth question.

Full route-by-route detail: `docs/requirements/01-architecture.md` §Full
API route reference.

## References
- `docs/requirements/01-architecture.md` §Network Binding & Security,
  §Full API route reference
- `docs/requirements/00-overview-and-goals.md` §Non-goals (multi-user/
  networked use)
