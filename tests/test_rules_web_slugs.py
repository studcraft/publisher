"""Tests for :mod:`publisher.rules_web.slugs`.

These pin public URLs. A change that makes one of these fail is a change that moves a
published address, which is why they are asserted literally rather than derived.
"""

from __future__ import annotations

import pytest

from publisher.rules_web import slugs


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("02-core-rules.md", "core-rules"),
        ("17-infantry.md", "infantry"),
        ("05-construction-components.md", "construction-components"),
        ("game-flow.md", "game-flow"),
        ("15-geometry-layers", "geometry-layers"),
    ],
)
def test_document_slug_strips_the_numeric_prefix_and_extension(name: str, expected: str) -> None:
    """The ruleset's internal ordering does not reach the published URL."""
    assert slugs.document_slug(name) == expected


@pytest.mark.parametrize(
    ("rule_id", "expected"),
    [("CORE-001", "core-001"), ("FLOW-013", "flow-013"), ("DMG-016", "dmg-016")],
)
def test_rule_slug_is_the_id_lowercased(rule_id: str, expected: str) -> None:
    """WordPress stores a lowercased slug, so that is what gets generated."""
    assert slugs.rule_slug(rule_id) == expected


def test_a_name_with_nothing_usable_in_it_fails() -> None:
    """A slug that came out empty would publish a page at its parent's own URL."""
    with pytest.raises(slugs.SlugError):
        slugs.document_slug("---")


def test_a_rule_id_with_nothing_usable_in_it_fails() -> None:
    """Same again for a rule: an empty slug is never a usable address."""
    with pytest.raises(slugs.SlugError):
        slugs.rule_slug("   ")


def test_the_rule_id_pattern_matches_what_the_ruleset_writes() -> None:
    """Citations are found by this pattern, so it has to match the real forms."""
    found = slugs.RULE_ID.findall("see CORE-001 and MOVE-017, but not CORE-1 or coRE-001")
    assert found == [("CORE", "001"), ("MOVE", "017")]
