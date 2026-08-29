"""Renderers, keyed by output format.

A renderer takes a :class:`~publisher.quicksheet.model.Document` and an exact destination
path, and writes that one file. It reads nothing else — not the ruleset, not the
specification file — so adding a format never touches the stages before it.

Renderers do not choose where they write. The destination comes from
:mod:`publisher.quicksheet.publish`, which derives it from the document's name, ruleset
version and language, so every format lands beside its siblings under one predictable tree.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from publisher.quicksheet import publish
from publisher.quicksheet.model import Document

Writer = Callable[[Document, Path], Path]


class RenderError(Exception):
    """Raised when a document cannot be rendered."""


class UnknownFormat(RenderError):
    """Raised when no renderer is registered for the requested format."""


@dataclass(frozen=True)
class Renderer:
    """One output format: what to call it, what it writes, and how."""

    name: str
    extension: str
    write: Writer


_RENDERERS: dict[str, Renderer] = {}


def register(name: str, extension: str, write: Writer) -> None:
    """Register a renderer for the format ``name``."""
    _RENDERERS[name] = Renderer(name=name, extension=extension, write=write)


def formats() -> tuple[str, ...]:
    """Return every registered format name, sorted."""
    return tuple(sorted(_RENDERERS))


def get(name: str) -> Renderer:
    """Return the renderer for ``name``, failing with the list of what exists."""
    try:
        return _RENDERERS[name]
    except KeyError:
        raise UnknownFormat(
            f"No renderer for format {name!r}. Available: {', '.join(formats()) or 'none'}."
        ) from None


def render(document: Document, fmt: str, root: Path = publish.ROOT) -> Path:
    """Render ``document`` to its derived publish path under ``root``."""
    renderer = get(fmt)
    destination = publish.path(document, renderer.extension, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return renderer.write(document, destination)


def _register_builtins() -> None:
    """Register the renderers that ship with the package."""
    from publisher.quicksheet.render import pdf

    register("pdf", pdf.EXTENSION, pdf.write)


_register_builtins()
