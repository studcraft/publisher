"""Publishing a rendered bundle to a WordPress site, and nothing else.

This package talks to a live system, so it is deliberately separate from the stages that do
not. It reads the bundle; it never reads the ruleset, the specification, or the document.
"""
