"""Native folder-picker bridge (`tkinter.filedialog`), called from Flask
(ADR-0006, docs/requirements/01-architecture.md §Why these specific
technology choices).

Not yet implemented -- this is Epic 6 work (docs/BACKLOG.md). Flask runs
natively on her machine (not sandboxed), so it can pop a real Windows
dialog and hand the chosen path back to the page, which is the whole
reason this bridge exists instead of relying on the browser's own file
input (browsers cannot open native OS folder pickers or read arbitrary
filesystem paths directly).
"""

from __future__ import annotations


def pick_folder(title: str = "") -> str | None:
    """Open a native folder-picker dialog and return the chosen path, or
    None if cancelled.

    Placeholder for Epic 6 -- raises NotImplementedError until then rather
    than returning a fake path, so nothing downstream can accidentally
    treat scaffolding as a real implementation.
    """
    raise NotImplementedError("backend.dialogs.pick_folder is Epic 6 work")
