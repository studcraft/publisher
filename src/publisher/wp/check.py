"""Establish that a site can be published to, before anything is written to it.

Publishing the ruleset is a few hundred writes. Finding out at write ninety that the user
cannot upload media, or that a firewall refuses POSTs to `/wp-json`, leaves the site half
published and the person running it guessing. Every question this asks is answerable by
reading, so it is asked first and answered without changing anything.

It also reports the one thing no error message would ever say out loud: which of the pages
this bundle wants to publish **already exist on the site, under something else**. `push`
adopts a page by slug, so a page somebody else made at `/movement` is a page `push` will
overwrite. That is worth seeing before it happens rather than after.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from publisher.wp.client import WordPress, WordPressError

# What publishing actually needs. `edit_theme_options` is only for the navigation menu, and
# is reported separately: an Editor can publish every page and still not write a menu.
REQUIRED = ("publish_pages", "upload_files")
MENU_CAPABILITY = "edit_theme_options"


@dataclass
class Finding:
    """One question asked of the site, and what it answered."""

    label: str
    ok: bool
    detail: str = ""

    def line(self) -> str:
        """Return the finding as one printable line."""
        mark = "ok  " if self.ok else "FAIL"
        return f"{mark}  {self.label}" + (f" — {self.detail}" if self.detail else "")


@dataclass
class Report:
    """Everything the check established."""

    findings: list[Finding] = field(default_factory=list)
    adopted: list[str] = field(default_factory=list)
    foreign: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing blocking was found. Collisions are reported, not blocking."""
        return all(finding.ok for finding in self.findings)

    def summary(self) -> str:
        """Return the whole report, as it is printed."""
        lines = [finding.line() for finding in self.findings]
        if self.adopted:
            lines.append(
                f"note  {len(self.adopted)} pages of this bundle are already on the site and "
                "will be updated in place"
            )
        if self.foreign:
            lines.append(
                f"WARN  {len(self.foreign)} pages already exist at a slug this bundle "
                "publishes, in a different place on the site. Pushing adopts a page by slug, "
                "so these would be overwritten: " + ", ".join(sorted(self.foreign))
            )
        return "\n".join(lines)


def check(bundle: dict, site: WordPress) -> Report:
    """Read everything needed to know whether ``bundle`` can be published to ``site``."""
    report = Report()

    if not _reachable(site, report):
        return report
    user = _identity(site, report)
    if user is None:
        return report
    _capabilities(user, report)
    _collisions(bundle, site, report)
    return report


def _reachable(site: WordPress, report: Report) -> bool:
    """Establish that the REST API answers at all."""
    try:
        site.reachable()
    except WordPressError as exc:
        report.findings.append(Finding("the REST API answers", False, str(exc)))
        return False
    report.findings.append(Finding("the REST API answers", True))
    return True


def _identity(site: WordPress, report: Report) -> dict | None:
    """Establish who the application password authenticates as."""
    try:
        user = site.me()
    except WordPressError as exc:
        report.findings.append(Finding("the application password authenticates", False, str(exc)))
        return None
    roles = ", ".join(user.get("roles") or ()) or "no role"
    report.findings.append(
        Finding("the application password authenticates", True, f"{user.get('name')} ({roles})")
    )
    return user


def _capabilities(user: dict, report: Report) -> None:
    """Establish that the authenticated user may do what publishing does."""
    granted = user.get("capabilities") or {}
    for capability in REQUIRED:
        report.findings.append(
            Finding(
                f"the user may {capability.replace('_', ' ')}",
                bool(granted.get(capability)),
                "" if granted.get(capability) else "publishing needs this",
            )
        )
    # Not blocking: `push` works without it, only `menu` does not.
    if not granted.get(MENU_CAPABILITY):
        report.findings.append(
            Finding(
                "the user may edit theme options",
                True,
                "absent — `push` and `promote` work, `menu` needs an administrator",
            )
        )


def _collisions(bundle: dict, site: WordPress, report: Report) -> None:
    """Report pages already on the site at a slug this bundle publishes."""
    try:
        existing = list(site.list_pages())
    except WordPressError as exc:
        report.findings.append(Finding("the site's pages can be listed", False, str(exc)))
        return
    report.findings.append(
        Finding("the site's pages can be listed", True, f"{len(existing)} pages")
    )

    by_id = {page["id"]: page for page in existing}
    wanted = {page["slug"]: page.get("parent") for page in bundle.get("pages") or []}

    for page in existing:
        slug = page.get("slug")
        if slug not in wanted:
            continue
        parent = by_id.get(page.get("parent") or 0)
        here = parent.get("slug") if parent else None
        if here == wanted[slug]:
            report.adopted.append(slug)
        else:
            report.foreign.append(f"{slug} (at {page.get('link') or page['id']})")
