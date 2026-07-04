# ADR-0011: PyInstaller single `.exe`, no code signing purchased

## Status
Accepted

## Context
The mother's use case requires zero setup beyond double-clicking a
desktop shortcut — no Python install, no terminal, no visible console.
An unsigned PyInstaller `.exe` triggers Windows SmartScreen's "Windows
protected your PC" warning on first run, which requires an unfamiliar
"More info → Run anyway" click-through — an OS-level dialog that appears
*before* the app's own webpage exists at all, so nothing built into the
app itself can address that specific moment.

A standard (OV) code-signing certificate does not suppress SmartScreen
immediately — Windows builds trust from download volume over time, so a
small family-scale app would likely still trigger the warning for a long
while even when signed. An EV certificate does get instant trust but
costs several hundred dollars/year and requires business verification.

## Decision
Package as a single PyInstaller `.exe`. **Do not purchase code
signing** (neither OV nor EV) — the cost/benefit doesn't justify it at
this project's scale (family use, portfolio piece, not public
distribution). Instead:

- **Primary mitigation:** whoever installs the app for her (a technical
  family member) runs the `.exe` once themselves and clicks through
  "More info → Run anyway." Windows remembers that specific `.exe` was
  explicitly allowed on that machine and does not ask again — this
  follows the same pattern already used for AI key provisioning
  (ADR-0003): front-load one-time technical friction onto whoever sets
  the machine up, not onto her.
- **Fallback**, for the rare case she reinstalls without help nearby: a
  short local HTML file (matching the project's own tech stack) with two
  sentences and one screenshot showing exactly what to click, living as
  a separate file next to the shortcut — since it can't be shown inside
  the app itself (the timing problem above still applies).

## Consequences
- Zero signing cost, no business-verification process, no annual renewal
  to maintain.
- SmartScreen click-through becomes a one-time, front-loaded technical
  step rather than something recurring or something she has to navigate
  personally — consistent with how the design generally handles
  unavoidable technical friction elsewhere.
- If the project's distribution scope ever changes (e.g. broader public
  distribution beyond "public GitHub portfolio repo plus direct family
  use"), this decision should be revisited — the cost/benefit
  calculation here is explicitly scoped to the current, small audience.
- Depends on the "someone technical sets it up first" assumption holding
  in practice, same dependency noted for AI-key pre-filling — if that
  assumption breaks (e.g. she reinstalls entirely alone), the fallback
  HTML file is the only safety net, and it's a lesser experience than
  never seeing the dialog at all.

## Alternatives Considered
- **Purchase an OV certificate** — rejected: doesn't solve the actual
  problem (instant trust) at this project's expected download volume;
  cost without proportional benefit.
- **Purchase an EV certificate** — rejected: does solve the problem
  immediately, but at a cost (several hundred dollars/year, business
  verification) wildly disproportionate to a family-scale, non-monetized
  tool.
- **Build a proper installer (MSI, etc.)** — rejected alongside signing,
  for the same cost/benefit reasoning: a plain `.exe` + desktop shortcut
  is sufficient at this deployment's scale, and an installer doesn't by
  itself solve SmartScreen anyway.

## References
- `requirements/07-packaging-deployment.md` §Windows SmartScreen,
  §Explicitly out of scope for v1
