# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`octools` is the OpsCogs shared package for agent tools: the `OCTool` descriptor (`python/src/octools/descriptor.py`), result envelopes with the closed `column_kinds` vocabulary and the tolerant `read_envelope` (`envelopes.py`), the opt-in `validate_tabular` cell check (`cells.py`), pydantic-to-JSON-Schema helpers and the strict-clean checker (`schema.py`), a conformance validator (`validate.py`), and pure-dict converters to MCP and Anthropic tool shapes (`convert.py`). `SPEC_VERSION` (`"1.1"`) is the format version of the descriptor and envelopes; readers check the major only. Within a major, a minor may add only what a tolerant reader can drop or read as a fallback (an optional field whose absence keeps its meaning, a vocabulary value with a declared fallback, a helper or export); anything else needs a new major (`OCTL-0006`). The 1.x public API is exactly `octools.__all__`.

**Dependency direction is a hard rule.** `octools` depends on `pydantic` only. Every OpsCogs library may depend on `octools`; `octools` never imports any OpsCogs package and never grows an SDK dependency (`mcp`, `anthropic`, `openai`). Converters stay plain dicts.

Decision records live in `docs/decisions/OCTL-*.md` and are indexed in `docs/decisions/decision-log.md`. `OCTL-0001` defines the descriptor spec and records every deliberate deviation from its sources; `OCTL-0002` adds result paging (`total_count`, `next_cursor`); `OCTL-0004` adds `merge_providers`; `OCTL-0005` adds the `ip_block` / `big_integer` kinds, `column_scales` and `validate_tabular`; `OCTL-0006` adds `read_envelope`, per-vocabulary fallbacks and the compatibility contract. The 1.x scope fence in `OCTL-0001` (timeouts, cost hints, `input_examples`, `strict` flags, `openWorldHint`, approval class, redaction, async, streaming, non-JSON content, per-tool `version`) is amended only by a new decision record, never by a quiet field. New validator rules ship opt-in within a major, and every closed vocabulary declares a fallback.

Consumers file shared-tool asks as GitHub issues on `opscogs/octools` through the upstream request form, titled with a consumer-issued `<PREFIX>-UR-NNNN` id (`docs/dev/upstream_requests.md`). Check open requests with `gh issue list --repo opscogs/octools --label upstream-request --state open` when starting overlapping work, when planning a release, and when cutting the changelog. Cite the `UR` id in `CHANGELOG.md` for every request a release delivers: on the release tag, CI moves each open `ur:planned` request in the tag's milestone whose id that entry cites to `ur:delivered` (`scripts/deliver_upstream_requests.py`). Regenerate `docs/dev/upstream/requests.jsonl` with `scripts/sync_upstream_requests.py` at those two release moments; CI runs its `--check` on every push and fails a tag build whose mirror is stale. Nothing on the 1.x fence is added without a new decision record.

## Layout

Monorepo (`OCTL-0008` records the decision):

- `python/` - the PyPI package (`pyproject.toml`, `src/octools`, `tests`); build with `python -m build python`.
- `spec/` - the language-neutral contract: generated JSON Schema and vocabulary (`scripts/sync_spec.py`) plus curated fixtures every implementation must pass. Regenerate after any model change; `pytest` fails while it is stale.
- `typescript/` - the npm package `@opscogs/octools`, arriving with full parity; versions move in lockstep with `python/`.
- `scripts/` - repo tooling and `scripts/tests`. `docs/` - site, decisions, design, dev.
- The root `pyproject.toml` holds tool config only (ruff, black, mypy, pyright, coverage, pytest).

## Environment

Run `python`, `pytest`, `ruff`, `black`, `mypy` and `mkdocs` only inside the project venv (`source .venv/bin/activate` in the same shell, or `uv run`; rule `venv-activate`). Install everything (dev + doc + test extras): `pip install -e "./python[all]"`. Python 3.12 is required.

## Commands

```sh
pytest                                   # full suite; pyproject addopts already add --cov=src + term-missing + html
pytest python/tests/unit_tests/test_validate.py -v
pytest python/tests/unit_tests/test_version.py::test_version_file    # single test
ruff check && ruff format --check        # exactly what CI runs
ruff check --fix && ruff format          # fix
mypy python/src
npx prettier python/src spec typescript --check   # CI checks these; npm ci first
npx cspell "docs/**/*.md" "README.md" "python/src/**/*.md" "spec/**/*.md" "typescript/*.md"   # CI spellchecks docs + README (add words to .cspell/custom-words.txt)
python scripts/sync_spec.py [--check]    # regenerate spec/ after a model change; CI runs --check
npm --prefix typescript run docs -- --out ../docs/site/api/typescript   # TypeDoc into the site; needed before mkdocs
mkdocs build --strict                    # docs must build clean; CI gates on this
npm ci                                   # root workspace install (dependency changes need npm >= 11.21)
npm --prefix typescript run typecheck && npm --prefix typescript run lint
npm --prefix typescript run test:coverage   # spec/ fixtures + unit tests, 100% coverage gate
npm --prefix typescript run build && npm --prefix typescript run docs
```

Coverage has `fail_under = 100`, so `pytest` fails the build on a coverage drop, not just on test failures.

## Versioning

Two packages ship from one tag, in lockstep (`OCTL-0008`): PyPI `octools` and npm `@opscogs/octools`. Tags have no `v` (`1.2.0`) and are finals or PEP 440 pre-releases (`1.2.0rc1`). `scripts/release_version.py <tag>` maps the tag to the PyPI version, the npm semver (`1.2.0-rc.1`) and the npm dist-tag (`latest` for finals, `next` for pre-releases); `--check` asserts `python/src/octools/VERSION` and `typescript/package.json` carry them.

The repo never commits `python/src/octools/VERSION` (gitignored, written by CI) or an npm version other than `0.0.0`. `__init__.py` falls back to `0.0.0` when `VERSION` is absent. `python/tests/unit_tests/test_version.py` deletes and rewrites that file, so it appears and disappears during a test run. Non-tag pushes only run checks; contributors never bump versions.

A tag runs `build_package`, then `publish_pypi` and `publish_npm` (OIDC trusted publishing, no stored tokens), then `github_release`, then `deploy_docs` and `deliver_upstream_requests` (both finals only). `CHANGELOG.md` is the release record (`scripts/changelog_version.py --check-tag`): a final tag must equal the top `## [X.Y.Z] - YYYY-MM-DD` entry, so date that entry first; a pre-release tag (`X.Y.ZrcN`) must match that entry's version, dated or `Unreleased`. Entries are concise lines for released work only; do not log pre-merge fixes to unpublished work. Runbook, recovery and one-time setup: `docs/dev/releasing.md`.

## Docs layout

- `docs/site/` - published, user-facing docs (this is `docs_dir` for mkdocs). Assets go in `docs/site/assets/`, referenced relatively (`./assets/x.png`). Every page is listed in `mkdocs.yml` `nav`.
- `docs/decisions/` - architecture decision records in MADR 4.0 format (`README.md` there has the rules, `adr-template.md` the skeleton). Front matter carries `status` (`proposed`, `accepted`, `rejected`, `deprecated`, `superseded by OCTL-NNNN`), a per-record semver `version`, `date` and `decision-makers`; they have no `Version:` line under the H1. Every change bumps the record's version once per commit and updates the decision log's Current decisions row and History table (rule `decision-versioning`). Unpublished.
- `docs/design/` - design notes and working documents. Do **not** put user-facing docs or decision records here.
- `docs/dev/` - internal developer docs (onboarding). Outside the mkdocs `docs_dir`, but public: it follows the same vendor-neutral and no-internal-names rules as published docs.
- One H1 per file, a `Version: **X.Y.Z** · Date: YYYY-MM-DD` line under the H1 (decision records use front matter instead), ATX headings, language-tagged code fences (prefer `sh` for shell), relative internal links.
- Decision-record IDs stay **uppercase** wherever a person sees them: filenames and H1s are `OCTL-NNNN-...`, never `octl-` (rule `decision-ids-uppercase`).
- **No historical narrative** in docs, decision records, docstrings or comments (rule `no-historical-narrative`).

## Code style

- Ruff is the linter and formatter (line length 88, py312). Enabled rule sets include `ANN` (annotations; bare `Any` in a signature is rejected - use `object` and narrow), `D` (pydocstyle, pep257 convention), `ARG`, `B`, `C90`, `SIM`, `UP`, `I`. Tests are exempt from `ANN` and `D`.
- Every module and function needs a docstring outside `tests/` directories.
- **Minimal blank lines** (rule `no-extra-blank-lines`).

## Testing conventions

Prefer `@pytest.mark.parametrize` over duplicated test functions; use fakes (a small provider class, an in-memory sink) rather than mocks; drive tests through the public API (`octools` root imports) so the integration path is exercised; target full coverage. `octools.example` (`python/src/octools/example.py`) is the end-to-end fixture and a shipped demo provider (`octools list octools.example`), outside `octools.__all__`: a paged records tool, its deprecated alias, a tabular tool and an artifact tool that must always pass `validate_provider` and round-trip through both converters. Findings are data - a conformance test asserts `validate_provider(p) == []`, never a truthy check.

## Claude Code configuration

`.cursor/rules/*.mdc` is the source of truth. `scripts/sync_claude_config.py` generates `.claude/rules/*.md` from it (a Cursor `globs` value becomes `paths`); the rules named above load from there. Edit the `.cursor` file, then run `python scripts/sync_claude_config.py`; `pytest` fails while the generated files are out of date (`--check`).
