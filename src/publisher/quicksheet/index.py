"""Read the pinned StudCraft ruleset through upstream's own parser.

Upstream's ``scripts/parse_ruleset.py --json`` is the only feed. Writing a second Markdown
parser here would drift from theirs, which upstream's own documentation warns against.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from publisher.sync import SyncError, read_lock

PARSER_SCRIPT = Path("scripts/parse_ruleset.py")

_DOCUMENT_FIELDS = ("name", "path", "root")
_NODE_FIELDS = ("blocks", "children", "line", "line_end", "rule_id", "title")
_BLOCK_FIELDS = ("kind", "line_start", "line_end", "lines")


class RulesetError(Exception):
    """Base class for failures reading the ruleset."""


class FeedError(RulesetError):
    """Raised when upstream's parser fails or returns an unexpected shape."""


class UnknownRuleError(RulesetError):
    """Raised when a requested rule ID is not present in the pinned ruleset."""


class PinError(RulesetError):
    """Raised when the clone on disk is not at the commit the lock file pins."""


@dataclass(frozen=True)
class Block:
    """One typed span of a rule body, as upstream's parser reports it."""

    kind: str
    line_start: int
    line_end: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Rule:
    """One numbered rule, located in the document it came from."""

    id: str
    title: str
    doc: str
    line: int
    line_end: int
    blocks: tuple[Block, ...]


def _require(mapping: object, fields: tuple[str, ...], where: str) -> dict:
    """Return ``mapping`` as a dict, failing when it is not one or a field is missing."""
    if not isinstance(mapping, dict):
        raise FeedError(f"Expected an object at {where}, got {type(mapping).__name__}.")
    for field in fields:
        if field not in mapping:
            raise FeedError(f"Missing field {field!r} at {where}.")
    return mapping


def run_parser(clone_root: Path) -> dict:
    """Run upstream's parser inside ``clone_root`` and return its parsed JSON output.

    The parser resolves ``docs/`` from its own location rather than from the working
    directory, so the absolute script path is what selects the ruleset. ``cwd`` is set
    anyway, defensively, so that an upstream change to cwd-relative resolution cannot
    silently read a different tree.
    """
    script = clone_root / PARSER_SCRIPT
    if not script.exists():
        raise FeedError(f"Upstream parser not found at {script}.")
    result = subprocess.run(
        [sys.executable, str(script.resolve()), "--json"],
        cwd=clone_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FeedError(
            f"{PARSER_SCRIPT} exited {result.returncode}: {result.stderr.strip() or '<no stderr>'}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FeedError(f"{PARSER_SCRIPT} did not return valid JSON: {exc}") from exc


def _walk(node: dict, where: str) -> list[dict]:
    """Return ``node`` and every descendant, validating each on the way down."""
    _require(node, _NODE_FIELDS, where)
    found = [node]
    for position, child in enumerate(node["children"]):
        found.extend(_walk(child, f"{where}.children[{position}]"))
    return found


def build_index(clone_root: Path) -> dict[str, Rule]:
    """Return every rule in the pinned ruleset, keyed by rule ID."""
    return read_ruleset(clone_root)[0]


def read_ruleset(clone_root: Path) -> tuple[dict[str, Rule], tuple[str, ...]]:
    """Return the rule index and the glossary terms, parsing the ruleset once."""
    payload = run_parser(clone_root)
    if not isinstance(payload, dict):
        raise FeedError(f"Expected an object at the top level, got {type(payload).__name__}.")
    return _rules_from(payload, clone_root), _glossary_from(payload)


def _glossary_from(payload: dict) -> tuple[str, ...]:
    """Return the glossary's defined terms, longest first.

    The glossary document is found by its heading rather than by filename, so renumbering
    ``14-glossary.md`` does not silently drop every term. Longest first is what makes
    matching work: "Attack Roll" must win over "Attack Dice" sharing a first word, and
    "Weapon Front Footprint" over "Weapon Front".
    """
    for name in sorted(payload):
        document = payload[name]
        if not isinstance(document, dict) or not isinstance(document.get("root"), dict):
            continue
        for top in document["root"].get("children", []):
            if top.get("level") != 1 or top.get("title") != "Glossary":
                continue
            terms = [
                entry["title"]
                for entry in top.get("children", [])
                if entry.get("level") == 2 and entry.get("rule_id") is None and entry.get("title")
            ]
            return tuple(sorted(set(terms), key=lambda term: (-len(term), term)))
    return ()


def _rules_from(payload: dict, clone_root: Path) -> dict[str, Rule]:
    """Return every rule in ``payload``, keyed by rule ID."""
    rules: dict[str, Rule] = {}
    for name in sorted(payload):
        document = _require(payload[name], _DOCUMENT_FIELDS, name)
        for node in _walk(document["root"], f"{name}.root"):
            rule_id = node["rule_id"]
            if rule_id is None:
                continue
            blocks = []
            for position, raw in enumerate(node["blocks"]):
                block = _require(raw, _BLOCK_FIELDS, f"{name}.{rule_id}.blocks[{position}]")
                blocks.append(
                    Block(
                        kind=block["kind"],
                        line_start=block["line_start"],
                        line_end=block["line_end"],
                        lines=tuple(block["lines"]),
                    )
                )
            rules[rule_id] = Rule(
                id=rule_id,
                title=node.get("rule_title") or node["title"],
                doc=document["name"],
                line=node["line"],
                line_end=node["line_end"],
                blocks=tuple(blocks),
            )
    if not rules:
        raise FeedError(f"No rules found in {clone_root}. The feed parsed but carried no rule IDs.")
    return rules


def rule(index: dict[str, Rule], rule_id: str) -> Rule:
    """Return the rule with ``rule_id``, failing by name when it is absent."""
    try:
        return index[rule_id]
    except KeyError:
        raise UnknownRuleError(f"Rule {rule_id} is not in the pinned ruleset.") from None


def verify_pin(clone_root: Path, lock_path: Path) -> str:
    """Return the pinned commit, failing when the clone on disk is not at it.

    Builds read the pin, never whatever the working clone happens to be at, so that bumping
    the ruleset is a reviewed change to a tracked file rather than a side effect of whenever
    someone last ran ``publisher.sync``.
    """
    if not clone_root.exists():
        raise PinError(f"No clone at {clone_root}. Run `python -m publisher.sync` first.")
    try:
        pinned = read_lock(lock_path)["commit"]
    except SyncError as exc:
        raise PinError(str(exc)) from exc

    result = subprocess.run(
        ["git", "-C", str(clone_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PinError(f"Cannot read HEAD of {clone_root}: {result.stderr.strip()}")

    head = result.stdout.strip()
    if head != pinned:
        raise PinError(
            f"Clone at {clone_root} is at {head}, but {lock_path} pins {pinned}. "
            "Run `python -m publisher.sync --pinned` to return to the pinned commit."
        )
    return pinned
