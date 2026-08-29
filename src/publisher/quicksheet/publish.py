"""Where a rendered document is published.

The path is derived from the document, never chosen by the caller:

    publish/<name>/v<ruleset version>/<name>_<language>.<extension>

Deriving it is the point. A published artefact has to be findable from what it *is* — which
sheet, which ruleset version, which language — rather than from whatever directory the
person who ran the command happened to type. That is what makes the tree pushable to a
single source of truth and comparable across versions.
"""

from __future__ import annotations

import re
from pathlib import Path

from publisher.quicksheet.model import Document, DocumentError

ROOT = Path("publish")

_UNSAFE = re.compile(r"[^a-z0-9._-]+")


def slug(value: str) -> str:
    """Return ``value`` as a path-safe, lowercase token.

    Spaces vanish rather than becoming separators, so the ruleset version "0.2.0 Draft"
    reads as ``0.2.0draft`` — one token, sortable next to its neighbours, with no separator
    to guess wrong when someone types it by hand.
    """
    return _UNSAFE.sub("", value.strip().lower().replace(" ", ""))


def version_dir(document: Document) -> str:
    """Return the version directory name for ``document``."""
    version = slug(document.source.ruleset_version)
    if not version:
        raise DocumentError(
            "The document records no ruleset version, so it cannot be published: there "
            "would be nothing to distinguish it from a different version of the same sheet."
        )
    return f"v{version}"


def relative_path(document: Document, extension: str) -> Path:
    """Return the publish path for ``document`` in ``extension``, relative to the root."""
    name = slug(document.name)
    if not name:
        raise DocumentError("The document has no name, so it cannot be published.")
    language = slug(document.language)
    if not language:
        raise DocumentError(
            f"The document {name!r} declares no language. Publishing without one would "
            "collide with its own translations."
        )
    return Path(name) / version_dir(document) / f"{name}_{language}.{extension}"


def path(document: Document, extension: str, root: Path = ROOT) -> Path:
    """Return the full publish path for ``document`` under ``root``."""
    return root / relative_path(document, extension)
