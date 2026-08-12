# Agent Workflow

Guidance for working with minimal permission interruptions while staying safe. These are defaults, not blockers — unlike [Git Strategy](git-strategy.md), none of this is enforced by a hook, because every rule here has a legitimate exception.

## Prefer dedicated tools over Bash

A `Bash` call prompts for permission; `Read`, `Edit`, `Write`, `Grep`, `Glob` normally don't — so reach for those first.

In particular, never edit project files through the shell. `sed -i`, `awk`, `perl -pi`, `tee`, and output redirection all write blind: no read-before-write, and a pattern that matches twice silently changes the wrong thing. `Edit` fails loudly when its anchor isn't unique; that's a feature.

## When the shell is unavoidable

Prefer one bare command per `Bash` call — no `&&`/`;`/`||` chaining, no pipes, no `$(...)`/backtick substitution, no loops. A permission is granted by pattern; anything that makes the command dynamic can't be pre-authorized, however harmless it is. Split compound commands into separate calls instead of working around this.

This is a preference, not an absolute: the heredoc form for multi-line `git commit -m`/`gh pr create --body` (`$(cat <<'EOF' ... EOF)`), documented as the standard workflow for this harness, is a sanctioned exception — don't refuse to use it.

## `fewer-permission-prompts` skill

For a long or repetitive task, invoke it early, not at the end — it writes a prioritized allowlist into `.claude/settings.json` from the read-only calls you've been making. It only ever covers read-only commands; never let it authorize anything destructive. Read the existing `permissions` block first — its `deny` list is deliberate, and widening `allow` without understanding it is a policy change disguised as configuration.

## On denial

Don't retry the same command — a denial is a user decision, not a transient failure. In order: look for a dedicated tool, split a compound command into bare ones, and if still blocked, stop and report which command and why, instead of routing around it (including by asking another agent to run it).

## Autonomy

Gather what's needed from the user up front — file scope, expected behavior, how to verify, what's out of scope — rather than pausing mid-task for each question. After that:

- Obvious defaults: take them, and say so in the report.
- Ambiguous cases: pick the reasonable reading, state it as an explicit assumption, keep going.
- Only re-ask when two readings lead to materially different work, or the action is irreversible or external (delete, publish, push, merge).

Finish the whole task. If one part is blocked, do everything else and say clearly what's left out and why — narrowing scope is the user's call, not the agent's.

## Before reporting

Run whatever checks the project already has and report what they actually printed, not what was expected. If a number doesn't add up, stop and report it — never edit a file just to make a check pass. Call out what had to be interpreted versus what was given directly; each interpretation marks a spot where the task was underspecified.
