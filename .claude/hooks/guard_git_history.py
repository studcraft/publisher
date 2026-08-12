#!/usr/bin/env python3
"""PreToolUse guard for Bash: gate the git operations named in system/git-strategy.md.

Two categories:

- DENY — the history-rewriting operations banned outright. Blocked however the
  command is dressed up (git -C <dir> ..., cd x && git ..., env FOO=bar git ...).
- ASK — destructive but legitimate operations (reset --hard, clean -f,
  checkout -- <path>). They discard uncommitted work, so they need a human
  decision rather than the blanket "Bash(git *)" allow rule.

Matching parses the command instead of grepping it: the text is tokenized with
shell quoting rules, then every `git` token is read as an invocation (global
options skipped, subcommand and its arguments identified). A quoted argument is
a single token, so `git commit -m "never rebase"` is a commit, not a rebase —
grepping the raw string got that wrong. Heredoc bodies are stripped first,
since their words are not quoted into one token.

Input is the PreToolUse JSON payload on stdin; output is a decision, or nothing
to allow. Fails open on anything unexpected: a guard that blocks what it does
not understand gets switched off, and then nothing is enforced at all.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?\n\2(?=\n|$)", re.DOTALL)

# Shell operators that end one command and start the next.
_OPERATORS = {"&&", "||", ";", "|", "&", "(", ")", "{", "}", "<", ">", ">>", "<<", "|&"}

# git global options that consume the following token as their value.
_GLOBAL_OPTS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
}


def strip_heredocs(command: str) -> str:
    """Replace heredoc bodies with their delimiter, leaving the redirect intact."""
    return _HEREDOC.sub(lambda m: f"<<{m.group(2)}", command)


def tokenize(command: str) -> list[str]:
    """Split a shell command into tokens, keeping operators separate."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens: list[str] = []
    try:
        for token in lexer:
            tokens.append(token)
    except ValueError:
        pass  # Unterminated quote: keep what parsed, the subcommand comes early.
    return tokens


def is_git(token: str) -> bool:
    return token == "git" or token.endswith("/git")


def invocations(tokens: list[str]):
    """Yield (subcommand, arguments) for every git invocation in the token list."""
    for index, token in enumerate(tokens):
        if not is_git(token):
            continue
        rest: list[str] = []
        for following in tokens[index + 1 :]:
            if following in _OPERATORS or is_git(following):
                break
            rest.append(following)
        subcommand, arguments = split_subcommand(rest)
        if subcommand:
            yield subcommand, arguments


def split_subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:
    """Skip git's global options and return the subcommand and its arguments."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            return token, tokens[index + 1 :]
        index += 2 if token in _GLOBAL_OPTS_WITH_VALUE else 1
    return None, []


def has_long(arguments: list[str], prefix: str) -> bool:
    """True if some argument is `--flag` or `--flag=value`."""
    return any(arg == prefix or arg.startswith(prefix + "=") for arg in arguments)


def has_short(arguments: list[str], letter: str) -> bool:
    """True if some argument is a short-option cluster containing `letter`."""
    return any(re.fullmatch(r"-[A-Za-z]+", arg) and letter in arg[1:] for arg in arguments)


def is_force_push(arguments: list[str]) -> bool:
    return has_short(arguments, "f") or any(arg.startswith("--force") for arg in arguments)


DENY_RULES = [
    ("commit", lambda args: has_long(args, "--amend"), "git commit --amend"),
    ("push", is_force_push, "git push --force / --force-with-lease / -f"),
    ("rebase", lambda _args: True, "git rebase"),
    ("filter-branch", lambda _args: True, "git filter-branch"),
    ("reflog", lambda args: bool(args) and args[0] == "expire", "git reflog expire"),
    ("update-ref", lambda args: has_short(args, "d"), "git update-ref -d"),
    (
        "add",
        lambda args: has_short(args, "A") or has_long(args, "--all"),
        "git add -A / --all",
    ),
    ("add", lambda args: "." in args, "git add ."),
]

ASK_RULES = [
    ("reset", lambda args: has_long(args, "--hard"), "git reset --hard"),
    ("clean", lambda args: has_short(args, "f") or has_long(args, "--force"), "git clean -f"),
    ("checkout", lambda args: "--" in args, "git checkout -- <path>"),
    ("restore", lambda _args: True, "git restore"),
]


def allow() -> None:
    sys.exit(0)


def decide(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        allow()

    parsed = list(invocations(tokenize(strip_heredocs(command))))

    for subcommand, arguments in parsed:
        for name, matches, label in DENY_RULES:
            if subcommand == name and matches(arguments):
                decide(
                    "deny",
                    f"Blocked by system/git-strategy.md: `{label}` is a banned "
                    "git-history operation, regardless of flags or wrapping used to "
                    "phrase the command. History only grows in this repo — no exceptions.",
                )

    for subcommand, arguments in parsed:
        for name, matches, label in ASK_RULES:
            if subcommand == name and matches(arguments):
                decide(
                    "ask",
                    f"`{label}` discards uncommitted work in the tree, which cannot be "
                    "recovered from git. Confirm this is intended (see "
                    "system/git-strategy.md).",
                )

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # Fail open, deliberately.
