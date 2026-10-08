# Contributing to octools

Version: **1.0.1** · Date: 2026-10-08

Thank you for helping with `octools`, the shared package for agent tools. This
repository holds the Python package (`python/`, PyPI `octools`), the TypeScript
package (`typescript/`, npm `@opscogs/octools`) and the language-neutral
conformance contract (`spec/`). Everyone taking part follows the
[Code of Conduct](./CODE_OF_CONDUCT.md). Report security problems through the
[security policy](./SECURITY.md), never in a public issue.

## File an issue

Search open and closed issues first, then use an issue form:

- **Bug report**: the package and version, the smallest reproduction, expected
  against actual behavior.
- **Feature request**: the problem, your proposal, the language or languages
  involved, and whether it changes the wire format.
- **Upstream request**: only for downstream libraries that track their asks
  under their own decision-record prefix (`PREFIX-UR-NNNN`). Everyone else
  uses the feature request form.

For anything larger than a small fix, open an issue and agree on the approach
before you write code. Some changes are declined by design: the 1.x scope fence
in [OCTL-0001](./docs/decisions/OCTL-0001-descriptor-origin.md) (timeouts, cost
hints, `input_examples`, `strict` flags, `openWorldHint`, approval class,
redaction, async, streaming, non-JSON content, per-tool `version`) is amended
only by a new decision record, never by a quiet field. A proposal on the fence
starts as a decision record in `docs/decisions/`, using
`docs/decisions/adr-template.md` and the rules in the README beside it.

## Set up

Python 3.12 or later, and Node 22.18 or later. Changing npm dependencies needs
npm 11.21 or later.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e "./python[all]"
npm ci
```

`npm ci` at the repository root installs the TypeScript workspace plus
`prettier` and `cspell`. Run Python tools only inside the venv.

## Make a change

1. Fork the repository and create a branch from `main`.
2. Make the change with tests. Python code needs full coverage (`fail_under =
100`); the TypeScript suite also runs at 100% coverage against the `spec/`
   fixtures.
3. Run the checks below for the languages you touched.
4. Add a changelog bullet (see below).
5. Commit with a sign-off and push to your fork.
6. Open a pull request against `main` and fill in the template.

### Sign off your commits

Contributions are accepted under the [Developer Certificate of
Origin](https://developercertificate.org/). Sign every commit:

```sh
git commit -s -m "Describe the change"
```

This adds a `Signed-off-by: Your Name <you@example.com>` line, stating that you
have the right to submit the work under the MIT license. The DCO app checks
every pull request; to fix a missing sign-off, run `git commit --amend -s` (or
`git rebase --signoff main` for several commits) and force-push your branch.

### Review and merge

OpsCogs maintainers review every pull request, and every merge into `main` is
approved by a maintainer (see `.github/CODEOWNERS`). Pull requests are
squash-merged. CI must pass first.

## Checks

CI runs these on every pull request. Run them locally first.

```sh
# Python (inside the venv)
pytest
ruff check && ruff format --check
mypy python/src
python scripts/sync_spec.py --check
pytest scripts/tests

# Formatting and spelling
npx prettier python/src spec typescript --check
npx cspell "docs/**/*.md" "README.md" "python/src/**/*.md" "spec/**/*.md" "typescript/*.md"

# Docs
mkdocs build --strict
```

```sh
# TypeScript
cd typescript
npm run typecheck
npm run lint
npm run test:coverage
npm run build
```

`ruff check --fix && ruff format` fixes most Python style findings. Add a word
`cspell` flags to `.cspell/custom-words.txt` only when it is a real term.

Conventions to keep in mind:

- Python: `ruff` rules include annotations and docstrings (every module and
  function outside `tests/` needs a docstring); keep blank lines to the
  required minimum.
- Tests prefer `@pytest.mark.parametrize`, small fakes over mocks, and the
  public API (`octools` root imports).
- `octools` depends on `pydantic` only (and `zod` for TypeScript). It never
  imports an OpsCogs package or an SDK such as `mcp`, `anthropic` or `openai`,
  and converters return plain data.
- Examples, docs and tests stay generic: no vendor or product names.
- Docs describe what exists now, not how it got there. Each new markdown file
  has one H1 and a `Version: **X.Y.Z** · Date: YYYY-MM-DD` line under it.
- Write "catalog", not "catalogue".

## Changes that touch both languages

The wire format (the descriptor, envelopes, closed vocabularies and their
fallbacks, validator findings and converter output) is defined by the Python
models, and the TypeScript package must match it
([OCTL-0008](./docs/decisions/OCTL-0008-language-neutral-spec-and-typescript.md)).
A wire-format change lands in a single pull request that contains:

- the updated Python models and implementation,
- the regenerated `spec/` (`python scripts/sync_spec.py`; CI fails on a stale
  `spec/vocabulary.json` or `spec/schema/`),
- new or changed fixtures under `spec/fixtures/`, written by hand, with
  `description`, `input` and `expected`,
- the matching TypeScript implementation, passing every fixture.

No fixture is skipped or filtered by language. A change that cannot be
implemented in both languages in one pull request is not ready to merge. Within
a major version a minor release may add only what a tolerant reader can drop or
read as a declared fallback
([OCTL-0006](./docs/decisions/OCTL-0006-tolerant-readers.md)); anything else
needs a new major and a decision record.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Add one concise bullet, newest first, under `Added`, `Changed` or `Fixed` in the
Unreleased section, naming the user-visible behavior and the symbols a reader
would search for. Tag it with your issue as `GH-N`; maintainers replace or add
the internal tracker key at merge. Skip formatting-only changes and internal
renames.

## Releases

Maintainers cut releases by pushing a tag; one tag publishes the Python and
TypeScript packages at the same version. Contributors never bump a version,
edit `VERSION` or `package.json` versions, or date a changelog entry. Add your
bullet under Unreleased and a maintainer does the rest.

## License

By contributing you agree that your work is licensed under the [MIT
License](./LICENSE). The OpsCogs name and logos are not covered by it; see
[NOTICE](./NOTICE).
