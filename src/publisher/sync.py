"""Clone the StudCraft source repository into ``source/`` as the publish source of truth."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

SOURCE_REPO = "https://github.com/studcraft/studcraft.git"
DEFAULT_REV = "main"
DEST = Path("source/studcraft")
LOCK_PATH = Path("source/studcraft.lock.json")

_VERSION_HEADER = re.compile(r"^\*\*Version:\*\*\s*(.+?)\s*$", re.MULTILINE)


class SyncError(RuntimeError):
    """Raised when the cloned source is not in a state a build can be pinned to."""


def read_ruleset_version(clone_root: Path) -> str:
    """Return the ruleset version declared by the documents under ``clone_root``.

    The clone is shallow and carries no tags, so the version comes from the
    ``**Version:**`` header every ruleset document declares. All documents must agree;
    a disagreement is an upstream defect and is not resolved silently.
    """
    versions: dict[str, str] = {}
    for path in sorted((clone_root / "docs").glob("*.md")):
        match = _VERSION_HEADER.search(path.read_text(encoding="utf-8"))
        if match:
            versions[path.name] = match.group(1)

    if not versions:
        raise SyncError(f"No document under {clone_root / 'docs'} declares a **Version:** header.")

    distinct = sorted(set(versions.values()))
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={version!r}" for name, version in sorted(versions.items()))
        raise SyncError(f"Ruleset documents disagree on the version: {detail}")

    return distinct[0]


def write_lock(path: Path, repo: str, rev: str, commit: str, version: str) -> None:
    """Write the pin describing exactly which upstream ruleset a build may use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"commit": commit, "repo": repo, "rev": rev, "version": version}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_lock(path: Path = LOCK_PATH) -> dict[str, str]:
    """Return the pin recorded at ``path``."""
    if not path.exists():
        raise SyncError(f"No lock file at {path}. Run `python -m publisher.sync` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def clone_source(
    repo: str = SOURCE_REPO,
    rev: str = DEFAULT_REV,
    dest: Path = DEST,
    lock_path: Path = LOCK_PATH,
) -> str:
    """Clone ``repo`` at ``rev`` into ``dest``, replacing any existing checkout.

    Write the resolved pin to ``lock_path`` and return the resolved commit SHA. The lock
    file is written only once the clone has succeeded and its version has been read, so a
    failed clone leaves the previous pin intact.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", rev, repo, str(dest)],
        check=True,
    )
    result = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    write_lock(lock_path, repo=repo, rev=rev, commit=commit, version=read_ruleset_version(dest))
    return commit


def restore_pinned(lock_path: Path = LOCK_PATH, dest: Path = DEST) -> str:
    """Check out exactly the commit ``lock_path`` pins, replacing any existing checkout.

    This is what a build needs and what ``clone_source`` cannot give it: cloning a branch
    resolves to wherever that branch is now, which drifts away from the pin as soon as
    upstream moves. The lock file is read, never written.
    """
    pin = read_lock(lock_path)
    commit, repo = pin["commit"], pin["repo"]

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "remote", "add", "origin", repo], check=True)
    subprocess.run(
        ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit],
        check=True,
    )
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "FETCH_HEAD"], check=True)
    return commit


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and clone the source repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=SOURCE_REPO, help="Git URL to clone.")
    parser.add_argument("--rev", default=DEFAULT_REV, help="Branch or tag to clone.")
    parser.add_argument("--dest", type=Path, default=DEST, help="Target directory.")
    parser.add_argument("--lock", type=Path, default=LOCK_PATH, help="Lock file to write.")
    parser.add_argument(
        "--pinned",
        action="store_true",
        help="Check out the commit the lock file already pins, and leave the lock alone. "
        "This is what builds and CI use; without it the lock is rewritten from --rev.",
    )
    args = parser.parse_args(argv)

    if args.pinned:
        commit = restore_pinned(args.lock, args.dest)
        print(f"Restored {args.dest} to the pinned commit ({commit})")
        return 0

    commit = clone_source(args.repo, args.rev, args.dest, args.lock)
    print(f"Cloned {args.repo}@{args.rev} into {args.dest} ({commit})")
    print(f"Wrote pin to {args.lock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
