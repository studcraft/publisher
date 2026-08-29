"""Read and write ``document.json``, the web edition's editable middle stage.

Writing is deterministic — fixed key order, fixed indent, trailing newline — so the file
diffs cleanly in review and so two builds of the same ruleset produce the same bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from publisher.rules_web.model import Document, WebDocumentError

DEFAULT_NAME = "document.json"


def write(document: Document, path: Path) -> Path:
    """Write ``document`` to ``path`` and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def read(path: Path) -> Document:
    """Return the document at ``path``, failing by name on any problem."""
    if not path.exists():
        raise WebDocumentError(
            f"No document at {path}. Run `python -m publisher.rules_web extract` first."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WebDocumentError(f"{path} is not valid JSON: {exc}") from exc
    return Document.from_dict(payload)
