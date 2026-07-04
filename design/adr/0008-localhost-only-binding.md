# ADR-0008: Flask/waitress binds to `127.0.0.1` only — hard requirement, not a default

## Status
Accepted

## Context
The Flask API (ADR-0001) has no authentication layer of any kind, and it
can pop native file dialogs and read/write arbitrary paths on the host
filesystem on request. This was previously only an implicit assumption
("single-user, localhost-bound" mentioned in passing in
`requirements/00-overview-and-goals.md` and `08-open-questions-and-
assumptions.md`) rather than something the code itself enforced. An
accidental `0.0.0.0` bind — even a temporary one made for local
debugging convenience and never reverted — would expose this
unauthenticated, filesystem-capable surface to anything else on the same
home network: other devices, a compromised IoT device, or a neighbor
within wifi range, not just her own browser.

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

## References
- `requirements/01-architecture.md` §Network Binding & Security
- `requirements/00-overview-and-goals.md` §Non-goals (multi-user/
  networked use)
