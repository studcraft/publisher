# Testing

BLOCKER rule. A pull request that does not pass the suite does not merge, and neither does
one that adds code the suite does not reach.

## What is enforced

Both run inside `lint-and-test`, which is the **required** status check on `main`:

- **The suite passes.** `pytest`, every test, no exceptions.
- **Coverage does not fall below its floor.** Currently 92%, with branch coverage on. The
  floor lives in `pyproject.toml` under `[tool.coverage.report]`.

The floor is what the suite actually covered on the day the gate was added, rounded down —
not a number someone liked the look of. It can be raised. **Lowering it is a change to argue
for in review**, in its own commit, with the reason written down. That is the whole point of
it being a number in a tracked file rather than a habit.

## Why coverage rather than "did you add a test"

A gate that asks whether the diff touches `tests/` is cheap to satisfy without doing the
work, and it fails on work that is legitimately test-free: a rename, a docstring, a pure
refactor. It would teach people to route around it, which is worse than no gate.

Coverage asks the question that matters — is this code reached — and a refactor keeps it
while a new untested branch drops it.

It is a proxy, and worth knowing the limits of: a test that imports a module and asserts
nothing moves the number. Coverage catches code nothing runs; **review** catches code
nothing checks. The gate does not replace the second job.

## The hole that had to be closed first

Coverage measures what the tests import. A brand-new module that nothing references is not
measured at all — so an entire untested file could be added and the percentage would not
move. This was found by probing the gate, not by reasoning about it.

`tests/test_package_is_covered.py` imports every module under `src/publisher`, so an
unreferenced module is measured from then on and its untested lines count like everyone
else's. It walks the source tree on disk rather than through `pkgutil`: under an editable
install the package finder does not enumerate sub-packages, and `walk_packages` reported one
module out of ten — which would have made that file look like it was working.

**Before trusting a new gate, make it fail.** Add the thing it should catch, watch the build
go red, then take it away. A gate nobody has seen fail is a gate nobody knows the shape of.

## Running it

```bash
pytest                 # fast, and works on a subset: pytest tests/test_sync.py
pytest --cov           # adds the coverage report and the floor
```

Coverage is deliberately not in `addopts`. Running one test file would then report near-zero
coverage and fail, which trains people to pass `--no-cov`, and a habit of disabling the gate
locally is how it stops being enforced.

## What is not enforced yet

**The `generated-files` job is not a required check.** It holds the staleness gates and the
determinism comparisons, for the quick sheet and the web edition both, so today a pull
request with a stale `document.json` or a stale bundle can merge with the job red. A check
that exists is not a check that blocks: that is branch protection, set by hand, and nothing
in this repository can do it.

```bash
gh api repos/studcraft/publisher/branches/main/protection --jq '.required_status_checks.contexts'
```

**The WordPress end-to-end run is not a check at all, and deliberately so.** Publishing to
the local WordPress in [`tools/wordpress-local/`](../tools/wordpress-local/README.md) needs
Docker and a database, which `lint-and-test` does not have and should not grow. What it
proves — that WordPress lowercases a slug, that a `private` page returns 404 to a stranger,
that an upload lands where the bundle's placeholder expects — is proved once against real
WordPress and then pinned in unit tests against a substitute transport. That is what the
injectable transport in `publisher.wp` is for: everything except WordPress's own behaviour
is covered by the required job.

## Adding a check later

Any new required workflow must trigger on **every** pull request, with no `paths:` filter at
the `on:` level. GitHub does not treat "filtered out" as passed or skipped — the check stays
pending and blocks the merge forever. Filter inside the job instead: read the diff, decide,
always produce a result.
