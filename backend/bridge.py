"""Adapter: translates pipeline/ calls into HTTP request/response +
polling state for backend/app.py (ADR-0001, docs/design/PATTERNS.md §1).

Zero business logic belongs here -- if this file ever makes a decision
beyond translation, that's a bug, not a style preference (the same rule
applies to main.py's CLI Adapter role).

Not yet implemented -- this is Epic 6 work (docs/BACKLOG.md), including
the `derive_batch_state()` State Machine function specified in
docs/requirements/01-architecture.md §Status endpoint contract §State
derivation and sketched in docs/design/PATTERNS.md §1.
"""

from __future__ import annotations
