"""Every module must be reachable by the suite, and importing it must not misbehave.

This exists because of a hole found by probing rather than by reasoning: coverage measures
what the tests import, so a brand-new module that nothing references is invisible to it. A
whole untested file could be added and the coverage floor would not move at all.

Importing every module here closes that: an unreferenced module is measured from now on, so
its untested lines count against the floor like everyone else's.

The source tree is walked on disk rather than through ``pkgutil``. Under an editable
install the package's finder does not enumerate sub-packages, so ``walk_packages`` reported
one module out of ten — which would have made this file look like it was working.
"""

from __future__ import annotations

import importlib
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "publisher"


def module_names() -> list[str]:
    """Return every module under ``src/publisher``, as an importable dotted name."""
    names = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts[-1] == "__main__":
            continue  # Importing it would run the CLI.
        names.append(".".join(parts))
    return names


def test_the_walk_finds_the_whole_package() -> None:
    """Guard the guard: a walk that finds too little would make the next test vacuous.

    The count is deliberately compared against the files on disk rather than a number
    written here, so adding a module cannot make this pass by accident.
    """
    on_disk = {p for p in SOURCE_ROOT.rglob("*.py") if p.name != "__main__.py"}

    assert len(module_names()) == len(on_disk)
    assert "publisher.quicksheet.render.pdf" in module_names()


def test_every_module_imports() -> None:
    """Import each module, so coverage sees the ones no other test references.

    A module that cannot be imported at all fails here rather than at the first runtime
    that happens to need it.
    """
    for name in module_names():
        importlib.import_module(name)
