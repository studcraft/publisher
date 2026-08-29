"""Allow ``python -m publisher.quicksheet``."""

from publisher.quicksheet.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
