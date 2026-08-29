"""How a ruleset document and a rule become the path segments they are published at.

Derivation is the point. A published URL has to follow from what the thing *is* — which
document, which rule — rather than from a list someone maintains by hand, because a hand-kept
list is one edit away from moving a public URL by accident.

The one escape is an explicit override in ``spec.toml``, which exists for the opposite case:
upstream renumbering a document must *not* move its URL, and the override is where that is
said out loud.
"""

from __future__ import annotations

import re

# `02-core-rules.md` -> `core-rules`. The numeric prefix orders the ruleset for a reader of
# the repository and means nothing on the web; keeping it would put the ruleset's internal
# ordering into every published URL, where renumbering would then move them.
_DOCUMENT_NAME = re.compile(r"^(?:\d+[-_])?(?P<stem>.+?)(?:\.md)?$")

# A rule ID as the ruleset writes it: CORE-001, FLOW-013, DMG-016.
RULE_ID = re.compile(r"\b([A-Z]{2,5})-(\d{3})\b")


class SlugError(Exception):
    """Raised when a name cannot be turned into a slug."""


def document_slug(name: str) -> str:
    """Return the page slug for the ruleset document file ``name``.

    >>> document_slug("02-core-rules.md")
    'core-rules'
    """
    match = _DOCUMENT_NAME.match(name.strip())
    stem = match.group("stem") if match else ""
    slug = _normalise(stem)
    if not slug:
        raise SlugError(f"The document name {name!r} yields no slug.")
    return slug


def rule_slug(rule_id: str) -> str:
    """Return the page slug for ``rule_id``.

    Lowercase, because WordPress lowercases a slug on the way in whatever we send: generating
    the stored form ourselves is what keeps the repository's idea of a URL and the site's
    identical.

    >>> rule_slug("CORE-001")
    'core-001'
    """
    slug = _normalise(rule_id)
    if not slug:
        raise SlugError(f"The rule ID {rule_id!r} yields no slug.")
    return slug


def _normalise(value: str) -> str:
    """Return ``value`` lowercased, with runs of anything else collapsed to one hyphen."""
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
