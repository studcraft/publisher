#!/usr/bin/env python3
"""PreToolUse guard for Bash: refuse the git-history operations banned by
system/git-strategy.md, no matter how the command is dressed up.

Why this exists: permissions.deny in .claude/settings.json matches by
prefix against the whole command string — "Bash(git commit --amend*)" only
fires if the command literally starts with "git commit --amend". Anything
that changes what the command starts with (git -C <dir> ..., cd x && git
..., git --git-dir=... ..., env FOO=bar git ...) never matches the prefix,
and falls through to the broad "Bash(git *)" allow rule — silently
permitted, no prompt, no block. This hook inspects the command text as a
whole instead of anchoring at position 0, so it catches the operation
wherever it appears in the string.

Not a sandbox: a determined agent can still obfuscate a command past a
regex (command substitution, base64, etc). It closes the specific gap
above — an innocuous-looking prefix silently defeating a documented hard
rule — not every conceivable evasion. Combined with the "no compound Bash,
no substitution" guidance in system/agent-workflow.md, the obfuscations
that would defeat this are already against the rules on their own.

Input is the PreToolUse JSON payload on stdin. Output is either nothing
(allow) or a deny decision whose reason is what the agent reads instead of
running the command.

Fails open: a missing/unreadable command allows the call through. A guard
that blocks what it does not understand gets switched off, and then
nothing is enforced at all.

Heredoc bodies are stripped before matching: the sanctioned
`git commit -m "$(cat <<'EOF' ... EOF)"` pattern (system/agent-workflow.md)
routinely needs to describe these very operations in prose inside the
message body — matching there would block the commit for talking about
the rule, not for breaking it.
"""

import json
import re
import sys

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?\n\2(?=\n|$)", re.DOTALL)


def strip_heredocs(command: str) -> str:
    return _HEREDOC.sub(lambda m: f"<<{m.group(2)}", command)

RULES = [
    (
        re.compile(r"\bgit\b.*\bcommit\b.*--amend\b", re.DOTALL),
        "git commit --amend",
    ),
    (
        re.compile(r"\bgit\b.*\bpush\b.*(?:--force\b|--force-with-lease\b)", re.DOTALL),
        "git push --force / --force-with-lease",
    ),
    (
        re.compile(r"\bgit\b.*\bpush\b.*(?:^|\s)-f(?:\s|$)", re.DOTALL),
        "git push -f",
    ),
    (
        re.compile(r"\bgit\b.*\brebase\b", re.DOTALL),
        "git rebase",
    ),
    (
        re.compile(r"\bgit\b.*\bfilter-branch\b", re.DOTALL),
        "git filter-branch",
    ),
    (
        re.compile(r"\bgit\b.*\breflog\b.*\bexpire\b", re.DOTALL),
        "git reflog expire",
    ),
    (
        re.compile(r"\bgit\b.*\bupdate-ref\b.*(?:^|\s)-d(?:\s|$)", re.DOTALL),
        "git update-ref -d",
    ),
    (
        re.compile(r"\bgit\b.*\badd\b.*(?:(?:^|\s)-A(?:\s|$)|--all\b)", re.DOTALL),
        "git add -A / --all",
    ),
    (
        re.compile(r"\bgit\b.*\badd\b\s+\.(?:\s|$)", re.DOTALL),
        "git add .",
    ),
]


def allow():
    sys.exit(0)


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main():
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        allow()

    scanned = strip_heredocs(command)

    for pattern, label in RULES:
        if pattern.search(scanned):
            deny(
                f"Blocked by system/git-strategy.md: `{label}` is a banned git-history "
                "operation, regardless of flags or wrapping used to phrase the command "
                f"(matched: {command!r}). History only grows in this repo — no exceptions."
            )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # Fail open, deliberately.
