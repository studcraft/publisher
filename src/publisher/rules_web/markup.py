"""Turn a rule's Markdown body into the HTML a page carries.

Two transformations happen on the way, and both are done on the parser's token stream rather
than on the rendered HTML:

- **A rule ID becomes a link** to that rule's page. This is the largest single gain of
  publishing to the web: the ruleset cites its neighbours constantly, and on paper those
  citations are text a reader has to go and look up.
- **A ruleset document's filename becomes a link** to that document's page. The ruleset
  writes them as code spans — ``05-construction-components.md`` — and on the web a filename
  is a worse address than the page it names.
- **An image's ``src`` becomes a placeholder**, resolved when the image is uploaded.

Working on tokens is what makes this safe. A rule ID inside a code span is not a ``text``
token, so it is left alone without anyone having to write a rule about backticks; an image is
an ``image`` token with a real ``src`` attribute, so nothing has to guess at the shape of an
``<img>`` tag in a string. A regular expression over rendered HTML would get both wrong in
ways that only show up on the published page.

A document filename is the one thing linked *inside* a code span, and only when the span's
whole content is a filename this edition publishes. That exactness is what keeps it from
misfiring on the many code spans that are not references — ``4 × 3``, ``W × D UB``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from markdown_it import MarkdownIt
from markdown_it.token import Token

from publisher.rules_web.slugs import REFERENCE


class UnknownReference(Exception):
    """Raised when a rule body cites a rule ID the pinned ruleset does not contain."""


def parser() -> MarkdownIt:
    """Return the Markdown parser the whole edition is rendered with.

    CommonMark plus the two extensions the ruleset actually uses. Enabling a fixed set rather
    than a preset keeps the output pinned to what this code was written against: a preset
    that gains a rule in a later release would change published pages without a diff anyone
    reviewed.
    """
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


def render(
    markdown: str,
    *,
    links: Mapping[str, str],
    on_image: Callable[[str, str], str],
    where: str,
    skip: str | None = None,
    unpublished: frozenset[str] = frozenset(),
    documents: Mapping[str, str] = MappingProxyType({}),
) -> str:
    """Return ``markdown`` as HTML, with references linked and images made placeholders.

    ``links`` maps every published rule ID to the path of its page. A citation of an ID that
    is absent raises :class:`UnknownReference` — publishing a dead link instead would hide a
    ruleset error behind a page that renders perfectly well.

    ``unpublished`` holds rule IDs that exist in the ruleset but whose document this edition
    does not publish. Citing one is still a failure, because there is no page to link to, but
    it is a different mistake from citing a rule that does not exist and gets its own message.

    ``documents`` maps a ruleset document's filename to the path of its page. A code span
    holding one becomes a link; a code span holding anything else, including a filename this
    edition does not publish, is left exactly as it was. That is deliberately gentler than the
    rule above: every document with rules in it is published, so an unresolvable rule ID means
    a broken citation, while an unresolvable filename usually means a document — a glossary, a
    foreword — that this edition simply does not publish.

    ``on_image`` is called with the image's source path and alt text, and returns the filename
    to place in the page. ``skip`` is a rule ID not to link, so a rule's own page does not
    link to itself.
    """
    md = parser()
    tokens = md.parse(markdown)
    for token in tokens:
        if token.type == "inline" and token.children:
            token.children = _transform(
                token.children, links, on_image, where, skip, unpublished, documents
            )
    return md.renderer.render(tokens, md.options, {})


def _transform(
    children: list[Token],
    links: Mapping[str, str],
    on_image: Callable[[str, str], str],
    where: str,
    skip: str | None,
    unpublished: frozenset[str],
    documents: Mapping[str, str],
) -> list[Token]:
    """Return ``children`` with images placeheld and rule IDs linked."""
    out: list[Token] = []
    # A rule ID inside an existing link is already pointing somewhere deliberate; wrapping a
    # second anchor around it would produce nested anchors, which is invalid HTML.
    depth = 0
    for token in children:
        if token.type == "link_open":
            depth += 1
        elif token.type == "link_close":
            depth -= 1

        if token.type == "image":
            token.attrSet("src", _placeholder(on_image, token, where))
            out.append(token)
        elif token.type == "code_inline" and depth == 0 and token.content in documents:
            # The code span is kept inside the anchor, so the filename still reads as one.
            out.append(_open(documents[token.content], "document-reference"))
            out.append(token)
            out.append(Token("link_close", "a", -1))
        elif token.type == "text" and depth == 0:
            out.extend(_link_references(token, links, where, skip, unpublished, documents))
        else:
            out.append(token)
    return out


def _placeholder(on_image: Callable[[str, str], str], token: Token, where: str) -> str:
    """Return the placeholder for ``token``'s image, registering it on the way."""
    from publisher.rules_web.model import MEDIA_PLACEHOLDER

    source = token.attrGet("src") or ""
    if not source:
        raise UnknownReference(f"{where} embeds an image with no source.")
    alt = _alt_text(token)
    return MEDIA_PLACEHOLDER % on_image(str(source), alt)


def _alt_text(token: Token) -> str:
    """Return an image token's alt text.

    The parser keeps alt text as parsed children rather than as a string, because it can hold
    emphasis. Published alt text is plain, so the text nodes are joined and everything else
    dropped.
    """
    if token.children:
        return "".join(child.content for child in token.children if child.type == "text")
    return token.content


def _link_references(
    token: Token,
    links: Mapping[str, str],
    where: str,
    skip: str | None,
    unpublished: frozenset[str],
    documents: Mapping[str, str],
) -> list[Token]:
    """Return ``token`` split into text and links around every reference it mentions.

    Both kinds are found in one pass: a rule ID, and a document filename written as prose
    rather than as a code span. The ruleset does the latter in only a few places, but a
    reference is a reference — leaving those three unlinked because of how they were typed
    would be an odd thing for a reader to run into.
    """
    text = token.content
    matches = list(REFERENCE.finditer(text))
    if not matches:
        return [token]

    out: list[Token] = []
    cursor = 0
    for match in matches:
        found = match.group(0)
        if match.group("doc"):
            href = documents.get(found)
            if href is None:
                # A document this edition does not publish. Left as it was written.
                continue
            kind = "document-reference"
        else:
            if found not in links:
                raise UnknownReference(_missing(found, where, unpublished))
            if found == skip:
                continue
            href, kind = links[found], "rule-reference"

        if match.start() > cursor:
            out.append(_text(text[cursor : match.start()]))
        out.append(_open(href, kind))
        out.append(_text(found))
        out.append(Token("link_close", "a", -1))
        cursor = match.end()

    if cursor < len(text):
        out.append(_text(text[cursor:]))
    return out


def _open(href: str, kind: str) -> Token:
    """Return the opening tag of one reference link."""
    return Token("link_open", "a", 1, attrs={"href": href, "class": kind})


def _missing(rule_id: str, where: str, unpublished: frozenset[str]) -> str:
    """Return the message for a citation that cannot be linked."""
    if rule_id in unpublished:
        return (
            f"{where} cites {rule_id}, which exists in the ruleset but sits in a document "
            "this edition does not publish, so there is no page to link to. Publish that "
            "document, or the citation cannot be honoured."
        )
    return (
        f"{where} cites {rule_id}, which is not in the pinned ruleset. Either the rule was "
        "renumbered upstream or the citation is wrong; publishing it would put a dead link "
        "on the page."
    )


def _text(content: str) -> Token:
    """Return a plain text token carrying ``content``."""
    return Token("text", "", 0, content=content)
