"""Command-line entry point for the web edition of the ruleset.

The same three separable stages the quick sheet uses, for the same reason:

    extract   ruleset AST + spec.toml  ->  document.json
    render    document.json            ->  publish/<name>/v<version>/<name>_<lang>.wp.json
    build     both, for convenience

``render`` reads nothing but the document, so a hand-edited ``document.json`` can be
re-rendered without going near the ruleset — and the bundle it writes is the only thing the
publication stage ever reads.

Publishing the bundle to a site is deliberately not here: see ``python -m publisher.wp``.
Rendering is offline and reproducible, publishing talks to a live system, and folding the
two together would put a network failure inside the stage whose whole value is that it has
none.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from publisher.quicksheet.index import RulesetError, read_ruleset, verify_pin
from publisher.quicksheet.model import DocumentError, Source
from publisher.rules_web import document as document_io
from publisher.rules_web import extract as extraction
from publisher.rules_web import render as rendering
from publisher.rules_web import spec as specification
from publisher.rules_web.markup import UnknownReference
from publisher.rules_web.model import Document, WebDocumentError
from publisher.rules_web.slugs import SlugError
from publisher.sync import DEST, LOCK_PATH, SyncError, read_lock

DEFAULT_DATA = Path("data/rules_web")
SPEC_NAME = "spec.toml"

_FAILURES = (
    RulesetError,
    specification.SpecError,
    extraction.ExtractError,
    UnknownReference,
    SlugError,
    WebDocumentError,
    DocumentError,
    SyncError,
)


def spec_path(data_dir: Path) -> Path:
    """Return the authored specification file inside ``data_dir``."""
    return data_dir / SPEC_NAME


def document_path(data_dir: Path) -> Path:
    """Return the generated document inside ``data_dir``."""
    return data_dir / document_io.DEFAULT_NAME


def extract(clone_root: Path, lock_path: Path, data_dir: Path) -> Document:
    """Return the web document built from the pinned ruleset and the specification."""
    commit = verify_pin(clone_root, lock_path)
    pin = read_lock(lock_path)
    index, _ = read_ruleset(clone_root)
    return extraction.build(
        spec=specification.load(spec_path(data_dir)),
        index=index,
        source=Source(
            repo=pin.get("repo", ""),
            ruleset_version=pin.get("version", ""),
            commit=commit,
        ),
        clone_root=clone_root,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="Read the ruleset and write the document. Renders nothing."
    )
    _add_source_args(extract_parser)
    _add_data_arg(extract_parser)

    render_parser = subparsers.add_parser(
        "render", help="Render an existing document. Does not read the ruleset."
    )
    _add_data_arg(render_parser)
    _add_out_arg(render_parser)

    build_parser = subparsers.add_parser("build", help="Extract and render in one step.")
    _add_source_args(build_parser)
    _add_data_arg(build_parser)
    _add_out_arg(build_parser)

    args = parser.parse_args(argv)

    try:
        return _run(args)
    except _FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--clone", type=Path, default=DEST, help="Pinned ruleset clone.")
    parser.add_argument("--lock", type=Path, default=LOCK_PATH, help="Lock file to read.")


def _add_data_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help=f"Product data directory, holding {SPEC_NAME} and {document_io.DEFAULT_NAME}.",
    )


def _add_out_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        type=Path,
        default=rendering.publish.ROOT,
        help="Publication root. The path under it is derived from the document.",
    )


def _run(args: argparse.Namespace) -> int:
    """Run the parsed command and report what it produced."""
    if args.command == "render":
        source_file = document_path(args.data)
        document = document_io.read(source_file)
        written = rendering.render(document, args.out)
        print(f"Rendered {source_file} -> {written} ({len(document.pages)} pages)")
        return 0

    document = extract(args.clone, args.lock, args.data)
    written = document_io.write(document, document_path(args.data))
    print(f"Wrote {written} ({len(document.pages)} pages, {len(document.media)} images)")

    if args.command == "extract":
        return 0

    output = rendering.render(document, args.out)
    print(f"Rendered {written} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
