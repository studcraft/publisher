#!/usr/bin/env python3
"""Stand-in for upstream's ``scripts/parse_ruleset.py``, for tests.

The real parser resolves ``docs/`` from its own location, so it can never be pointed at a
fixture tree. This prints captured JSON in upstream's exact schema instead, which keeps the
tests exercising the real subprocess path without depending on the clone.
"""

import sys
from pathlib import Path

sys.stdout.write(Path(__file__).with_name("feed.json").read_text(encoding="utf-8"))
