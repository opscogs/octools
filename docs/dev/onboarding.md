# Onboarding

Version: **0.3.0** · Date: 2026-10-08

Developer setup for `octools`. This page is unpublished (`docs/dev/` is
outside the mkdocs `docs_dir`).

## Environment

Python 3.12 is required. Everything runs inside the project venv; never
call `python`, `pytest`, `ruff`, `mypy` or `mkdocs` from outside it.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e "./python[all]"
npm install
```

`./python[all]` pulls the `dev` (build, ruff, black, mypy), `doc` (mkdocs) and
`test` (pytest, pytest-cov) extras. `npm install` provides `prettier` and
`cspell`, which CI runs over `python/src/` and `spec/` and the markdown respectively.

## Commands

```sh
pytest                                   # coverage gate (fail_under 100) included via addopts
pytest python/tests/unit_tests/test_validate.py -v
ruff check && ruff format --check        # what CI runs
ruff check --fix && ruff format          # fix
mypy python/src
npx prettier python/src spec --check
npx cspell "docs/**/*.md" "README.md" "python/src/**/*.md" "spec/**/*.md"
python scripts/sync_spec.py --check          # regenerate without --check after a model change
npm --prefix typescript run docs -- --out ../docs/site/api/typescript   # TypeScript API pages; mkdocs --strict needs them
mkdocs build --strict
python -m build python                  # wheel to python/dist/; delete python/dist and python/build after
python scripts/changelog_version.py --latest
python scripts/sync_upstream_requests.py --markdown   # open request table; never commit stdout
```

## Layout

- `python/src/octools/` - `descriptor.py` (OCTool, ToolProvider), `schema.py`
  (pydantic to JSON Schema, strict-clean), `envelopes.py`, `convert.py`,
  `validate.py`, `findings.py`, `listing.py` and `__main__.py` (the
  `octools list` CLI), and `example.py`, the demo provider
  (`octools list octools.example`) that the docs quick start is a
  simplified version of and the tests use end to end.
- `python/tests/unit_tests/` - one test module per source module; `scripts/tests/` tests the repo scripts.
- `spec/` - generated JSON Schema, vocabulary and curated fixtures; `typescript/` - the npm package (arrives later).
- `docs/site/` - published pages; `docs/decisions/` - decision records
  (MADR, `OCTL-NNNN-*.md`, uppercase ids, indexed in the
  [decision log](../decisions/decision-log.md)); `docs/design/` - design
  notes; `docs/dev/` - this folder, including
  [upstream requests](./upstream_requests.md).

## Releasing

Maintainers cut releases; the full runbook (pre-flight, pre-release, final,
verification, failure recovery, one-time registry setup) is in
[releasing](./releasing.md). `CHANGELOG.md` is the release record, and
`octools.__version__` falls back to `0.0.0` when the gitignored
`python/src/octools/VERSION` is absent.
