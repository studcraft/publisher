"""Command-line entry point for the quick-play sheet pipeline.

The pipeline is three separable stages, and the CLI exposes them separately on purpose:

    extract   ruleset AST + spec.toml  ->  document.json
    render    document.json            ->  publish/<name>/v<version>/<name>_<lang>.<ext>
    build     both, for convenience

``render`` reads nothing but the document, so a hand-edited ``document.json`` can be
re-rendered — to any format — without going near the ruleset.

Each product keeps its two tracked files in one directory under ``data/``:

    data/quicksheet_3x3/spec.toml        authored: what the sheet says
    data/quicksheet_3x3/document.json    generated: what a renderer consumes

``--data`` names that directory, so the two can never be mismatched across products.

Rendered outputs are published, not scratch: the path under ``--out`` is derived from the
document's name, ruleset version and language, so a published tree can be pushed to a
single source of truth and compared across versions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from publisher.quicksheet import document as document_io
from publisher.quicksheet import publish
from publisher.quicksheet import render as renderers
from publisher.quicksheet.extract import SpecError, build_document, draft_spec, load_spec
from publisher.quicksheet.index import RulesetError, read_ruleset, verify_pin
from publisher.quicksheet.model import Document, DocumentError, Source
from publisher.sync import DEST, LOCK_PATH, SyncError, read_lock

# The data directory is tracked in git; the rendered outputs are not. That split is the
# point of having a middle stage at all: `git diff data/<product>/document.json` shows
# exactly which lines a ruleset bump changed, and a hand edit is a reviewable change rather
# than a file the next build silently overwrites. Renders are reproducible from it, so they
# stay throwaway.
DEFAULT_DATA = Path("data/quicksheet_3x3")
SPEC_NAME = "spec.toml"


def spec_path(data_dir: Path) -> Path:
    """Return the authored specification file inside ``data_dir``."""
    return data_dir / SPEC_NAME


def document_path(data_dir: Path) -> Path:
    """Return the generated document inside ``data_dir``."""
    return data_dir / document_io.DEFAULT_NAME


def extract(clone_root: Path, lock_path: Path, data_dir: Path) -> Document:
    """Return the document built from the pinned ruleset and the product's specification.

    The product name defaults to the data directory's own name, so the two cannot drift; a
    specification file may override it with an explicit ``name``.
    """
    commit = verify_pin(clone_root, lock_path)
    pin = read_lock(lock_path)
    index, glossary = read_ruleset(clone_root)
    return build_document(
        index=index,
        spec=load_spec(spec_path(data_dir)),
        source=Source(
            repo=pin.get("repo", ""),
            ruleset_version=pin.get("version", ""),
            commit=commit,
        ),
        glossary=glossary,
        name=data_dir.resolve().name,
    )


def draft(clone_root: Path, lock_path: Path, rule_ids: list[str]) -> str:
    """Return a mechanically drafted specification file for ``rule_ids``."""
    verify_pin(clone_root, lock_path)
    return draft_spec(read_ruleset(clone_root)[0], rule_ids)


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


def _add_render_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        type=Path,
        default=publish.ROOT,
        help="Publication root. The path under it is derived from the document.",
    )
    parser.add_argument(
        "--format", default="pdf", choices=renderers.formats(), help="Output format."
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
    _add_render_args(render_parser)

    build_parser = subparsers.add_parser("build", help="Extract and render in one step.")
    _add_source_args(build_parser)
    _add_data_arg(build_parser)
    _add_render_args(build_parser)

    draft_parser = subparsers.add_parser(
        "draft", help="Print a mechanically drafted spec file, for bootstrapping only."
    )
    _add_source_args(draft_parser)
    draft_parser.add_argument("rules", nargs="+", help="Rule IDs to draft lines for.")

    args = parser.parse_args(argv)

    try:
        return _run(args)
    except (RulesetError, SpecError, DocumentError, renderers.RenderError, SyncError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    """Run the parsed command and report what it produced."""
    if args.command == "draft":
        print(draft(args.clone, args.lock, args.rules))
        return 0

    if args.command == "render":
        source_file = document_path(args.data)
        document = document_io.read(source_file)
        written = renderers.render(document, args.format, args.out)
        print(f"Rendered {source_file} -> {written}")
        return 0

    document = extract(args.clone, args.lock, args.data)
    written = document_io.write(document, document_path(args.data))
    print(f"Wrote {written} ({len(document.glossary)} glossary terms)")

    if args.command == "extract":
        return 0

    output = renderers.render(document, args.format, args.out)
    print(f"Rendered {written} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
