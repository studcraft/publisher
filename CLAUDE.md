@AGENTS.md

<!--
Claude Code reads CLAUDE.md. It does not read AGENTS.md.

This file exists so that one import makes this repository's own instructions
load at the start of every Claude session. Everything it would otherwise say
already lives in AGENTS.md and the documents AGENTS.md points at.

Do not copy content into this file. system/documentation-standards.md
("What `system/` Is For") forbids a second copy of a rule anywhere: the copy
is what goes stale, and a shortened copy silently drops whichever rules it
left out. A pointer cannot drift.

Path-scoped instructions live in .claude/rules/ and load only when an agent
touches a matching file. Enforcement that does not depend on an agent reading
anything lives in .claude/settings.json.

This comment is stripped before the file enters an agent's context window, so
it costs no tokens.
-->