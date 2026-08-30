"""Command-line entry point for publishing a rendered bundle to WordPress.

    check     nothing is written; can this site be published to at all?
    push      bundle  ->  every page on the site, as `private`
    promote   the staged pages  ->  `publish`
    menu      bundle  ->  the site's navigation: Rules, and the documents under it

Two commands rather than one, because the gap between them is the review. Nothing here reads
the ruleset or the specification: the bundle is the only input, so what a pull request
reviewed is what the site receives.

Credentials come from the environment, never from a flag — an application password in a
command line ends up in shell history and in the process list:

    WP_BASE_URL=http://localhost:8080 WP_USER=admin WP_APP_PASSWORD='…' \\
        python -m publisher.wp push

The local harness writes exactly those three into ``tools/wordpress-local/.env``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from publisher.rules_web import render as rendering
from publisher.rules_web.cli import DEFAULT_DATA, document_path
from publisher.rules_web.document import read as read_document
from publisher.rules_web.model import WebDocumentError
from publisher.sync import DEST
from publisher.wp.check import check
from publisher.wp.client import Credentials, Pacing, WordPress, WordPressError
from publisher.wp.menu import MenuError
from publisher.wp.menu import write as write_menu
from publisher.wp.promote import PromoteError, promote
from publisher.wp.push import DEFAULT_ORPHAN_LIMIT, PushError, push

SITE_ENV = "WP_BASE_URL"
USER_ENV = "WP_USER"
PASSWORD_ENV = "WP_APP_PASSWORD"

_FAILURES = (WordPressError, PushError, PromoteError, MenuError, WebDocumentError, OSError)


class ConfigurationError(Exception):
    """Raised when the environment does not say where to publish, or as whom."""


def credentials(environment: dict[str, str]) -> Credentials:
    """Return the credentials ``environment`` describes, failing by name on any absence."""
    missing = [name for name in (SITE_ENV, USER_ENV, PASSWORD_ENV) if not environment.get(name)]
    if missing:
        raise ConfigurationError(
            f"{', '.join(missing)} not set. Publishing needs a site, a user and an "
            "application password; the local harness writes all three into "
            "tools/wordpress-local/.env."
        )
    return Credentials(
        site=environment[SITE_ENV],
        user=environment[USER_ENV],
        password=environment[PASSWORD_ENV],
    )


def bundle_path(data_dir: Path, out: Path) -> Path:
    """Return the bundle rendered from the document in ``data_dir``.

    Derived from the document rather than taken as a flag, so the command cannot be pointed
    at a bundle belonging to another ruleset version by mistake.
    """
    return rendering.path(read_document(document_path(data_dir)), out)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Read-only preflight: is this site reachable, authenticated and writable?",
    )
    _add_common_args(check_parser)

    push_parser = subparsers.add_parser(
        "push", help="Stage every page of the bundle on the site, as `private`."
    )
    _add_common_args(push_parser)
    push_parser.add_argument("--clone", type=Path, default=DEST, help="Pinned ruleset clone.")
    push_parser.add_argument(
        "--orphan-limit",
        type=int,
        default=DEFAULT_ORPHAN_LIMIT,
        help="Refuse to unpublish more than this many pages at once.",
    )

    promote_parser = subparsers.add_parser(
        "promote", help="Publish the staged pages. Sends nothing but a status."
    )
    _add_common_args(promote_parser)

    menu_parser = subparsers.add_parser(
        "menu",
        help="Write the site navigation: one entry per ruleset document, in reading order.",
    )
    _add_common_args(menu_parser)

    args = parser.parse_args(argv)

    try:
        return _run(args)
    except ConfigurationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except _FAILURES as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Product data directory.")
    parser.add_argument(
        "--out", type=Path, default=rendering.publish.ROOT, help="Publication root."
    )
    # Publishing the whole ruleset is a few hundred authenticated writes. Against a hosted
    # WordPress that burst is what a firewall reads as an attack, so the pace is a knob
    # rather than a constant, and slowing down is the first thing to try after a 403.
    parser.add_argument(
        "--pace",
        type=float,
        default=0.0,
        help="Seconds to wait between requests. Raise it when a site rate-limits.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=4,
        help="How many times to try a request the site answered with 429, 502, 503 or 504.",
    )


def _run(args: argparse.Namespace) -> int:
    """Run the parsed command and report what it did."""
    site = WordPress(
        credentials(dict(os.environ)),
        pacing=Pacing(interval=args.pace, attempts=args.attempts),
    )
    path = bundle_path(args.data, args.out)
    bundle = json.loads(path.read_text(encoding="utf-8"))

    if args.command == "check":
        report = check(bundle, site)
        print(f"Checked {site_label()} against {path}")
        print(report.summary())
        return 0 if report.ok else 1

    if args.command == "push":
        report = push(bundle, site, clone_root=args.clone, orphan_limit=args.orphan_limit)
        print(f"Staged {path} on {site_label()}")
    elif args.command == "menu":
        report = write_menu(bundle, site)
        print(f"Wrote the navigation on {site_label()}")
    else:
        report = promote(bundle, site)
        print(f"Promoted {path} on {site_label()}")

    print(report.summary())
    return 0


def site_label() -> str:
    """Return the site being written to, for the run's own output."""
    return os.environ.get(SITE_ENV, "the configured site")


if __name__ == "__main__":
    raise SystemExit(main())
