# Releasing

Version: **1.1.0** · Date: 2026-10-08

The release runbook for maintainers. One tag publishes both packages, the
PyPI distribution `octools` and the npm package `@opscogs/octools`, at the
same version ([OCTL-0008](../decisions/OCTL-0008-language-neutral-spec-and-typescript.md)).
This page is unpublished (`docs/dev/` is outside the mkdocs `docs_dir`).

## Versions and tags

Tags carry no `v` prefix: `1.2.0`. A tag is either a final (`X.Y.Z`) or a
PEP 440 pre-release (`X.Y.ZaN`, `X.Y.ZbN`, `X.Y.ZrcN`). The two registries spell
a pre-release differently, so `scripts/release_version.py <tag>` maps the tag
to both:

| Tag        | PyPI version | npm version     | npm dist-tag | GitHub release |
| ---------- | ------------ | --------------- | ------------ | -------------- |
| `1.2.0`    | `1.2.0`      | `1.2.0`         | `latest`     | final          |
| `1.2.0rc1` | `1.2.0rc1`   | `1.2.0-rc.1`    | `next`       | pre-release    |
| `1.2.0a1`  | `1.2.0a1`    | `1.2.0-alpha.1` | `next`       | pre-release    |
| `1.2.0b2`  | `1.2.0b2`    | `1.2.0-beta.2`  | `next`       | pre-release    |

`python scripts/release_version.py --check <tag>` asserts that
`python/src/octools/VERSION` and `typescript/package.json` carry those
versions. That is the lockstep gate. The repository never commits `VERSION`
or an npm version other than `0.0.0`; the pipeline stamps both in the build.

No registry token is stored anywhere. Both registries publish through
OIDC trusted publishing from the `ci_pipeline.yml` workflow.

## Pre-flight

Do these in a normal pull request before tagging.

1. List open upstream requests and note which the release delivers:

   ```sh
   gh issue list --repo opscogs/octools --label upstream-request --state open
   ```

2. Regenerate the request mirror in the same change:

   ```sh
   python scripts/sync_upstream_requests.py
   ```

   CI runs its `--check` on every push and fails a tag build whose mirror is
   stale.

3. Cite each delivered request as `(PREFIX-UR-NNNN)` at the end of its
   changelog bullet. On the release tag, CI moves every open `ur:planned`
   request in the tag's milestone whose id the changelog cites to
   `ur:delivered`.
4. Replace the `Unreleased` marker on the top `CHANGELOG.md` entry with the
   release date. The entry's version must equal the tag's `X.Y.Z`; for a
   pre-release the entry is the one the final will carry. Check it:

   ```sh
   python scripts/changelog_version.py --latest
   ```

5. Run the checks from [onboarding](./onboarding.md) (`pytest`,
   `ruff check`, `mypy python/src`, `python scripts/sync_spec.py --check`,
   the TypeScript checks, `mkdocs build --strict`) and merge.

## Cut a pre-release first

Release a candidate before the final. A pre-release goes to PyPI as a
PEP 440 pre-release and to npm under the `next` dist-tag; `pip install
octools` and `npm install @opscogs/octools` do not pick it up. TestPyPI is not
used.

```sh
git switch main && git pull
git tag 1.2.0rc1
git push origin 1.2.0rc1
```

Verify the candidate (see [Verify](#verify)), then fix forward with `rc2` if
needed. Docs are not deployed for a pre-release.

## Cut the final

With the changelog entry dated and the candidate verified:

```sh
git switch main && git pull
git tag 1.2.0
git push origin 1.2.0
```

## What the tag jobs do

| Job                         | What it does                                                                                                                                                                                                                                              |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_package`             | Gates the tag against the changelog, writes `VERSION`, builds the sdist and wheel, stamps the npm version, runs `npm pack`, checks both versions with `release_version.py --check`, smoke-installs both artifacts and uploads them as workflow artifacts. |
| `publish_pypi`              | Environment `pypi`. Publishes the sdist and wheel by trusted publishing, with attestations.                                                                                                                                                               |
| `publish_npm`               | Environment `npm`. Publishes the tarball by trusted publishing with `--provenance`, under dist-tag `latest` (finals) or `next` (pre-releases).                                                                                                            |
| `github_release`            | After both publishes. Creates the GitHub release with the wheel, sdist and tgz as assets; pre-releases are flagged as such.                                                                                                                               |
| `deploy_docs`               | Finals only. Builds the TypeDoc pages and runs `mkdocs gh-deploy`.                                                                                                                                                                                        |
| `deliver_upstream_requests` | Finals only: moves cited `ur:planned` requests in the tag's milestone to `ur:delivered`.                                                                                                                                                                  |

`publish_pypi` and `publish_npm` run in parallel. Each environment waits for a
maintainer approval before its job starts.

## Verify

Use a clean directory and venv, and wait for the registry index to catch up.

```sh
python -m venv /tmp/verify && /tmp/verify/bin/pip install "octools==1.2.0"
/tmp/verify/bin/python -c "import octools; print(octools.__version__)"
npm view @opscogs/octools dist-tags
npm view @opscogs/octools@1.2.0 version
npm install @opscogs/octools@1.2.0 zod
```

For a pre-release, pin the exact version (`octools==1.2.0rc1`,
`@opscogs/octools@next`). Then confirm:

- `npm view @opscogs/octools dist-tags` shows `latest` on the new final, or
  `next` on the candidate, and `latest` unchanged by a pre-release.
- The npm package page shows the provenance badge, and the PyPI file page
  lists the attestation.
- The GitHub release carries the three assets.
- For a final, the docs site shows the new version.

## Failure recovery

PyPI and npm both reject a second upload of an existing version. Never delete
and re-push a tag to retry.

- **One registry published, the other failed.** Re-run the failed job from the
  workflow run page ("Re-run failed jobs"). The tag, the artifacts and the
  published half stay as they are. `github_release` and `deploy_docs` follow
  once both publishes succeed.
- **The build failed before any publish.** Fix on `main`, delete the unpublished
  tag locally and on the remote, and tag again at the same version. This is
  safe only while neither registry holds that version.
- **A broken release shipped.** Yank the release on PyPI (the project's
  "Manage" page, "Yank") and run `npm deprecate @opscogs/octools@1.2.0
"<reason, fixed in 1.2.1>"`. Then release a patch (`1.2.1`) through the same
  flow. Do not unpublish.

## One-time setup

Done once per repository by an owner of the `opscogs` GitHub organization.

### GitHub environments

Create two environments under Settings, Environments:

- `pypi` and `npm`, each with required reviewers set to the OpsCogs
  maintainers.
- Each with a deployment rule that limits runs to release tags (a tag
  pattern covering `X.Y.Z` and its pre-release forms, not branches).

### PyPI trusted publisher

On PyPI, add a trusted publisher for project `octools`. If the project does not
exist yet, add it as a pending publisher under the account's publishing page;
the first tag then creates the project.

- Owner: `opscogs`
- Repository: `octools`
- Workflow: `ci_pipeline.yml`
- Environment: `pypi`

### npm trusted publisher

On npm, the `opscogs` organization owns the scope. Configure a trusted
publisher for `@opscogs/octools` with owner `opscogs`, repository `octools`,
workflow `ci_pipeline.yml` and environment `npm`.

An npm trusted publisher is configured from the package's settings page, so
the package must exist before the first OIDC publish. Bootstrap it once:

1. Confirm the `opscogs` npm organization exists and you are a member with
   publish rights.
2. Download the `npm-dist` artifact from a green `build_package` run on `main`
   (version `0.0.0`), then stamp and repack it locally as a bootstrap version:
   `npm version 0.0.1-bootstrap.0 --workspace typescript --no-git-tag-version`
   and `npm pack` in `typescript/`. Do not commit the version change.
3. `npm login` (with 2FA), then
   `npm publish opscogs-octools-0.0.1-bootstrap.0.tgz --access public --provenance=false --tag bootstrap`.
   `--provenance=false` is required outside CI because `publishConfig` asks for
   provenance. A bootstrap version keeps the first real release (for example
   `1.2.0rc1`) free for CI to publish with provenance.
4. Configure the trusted publisher above. Under allowed actions, keep
   `npm publish`.
5. Push the next release tag within two days; a new trusted-publisher
   configuration expires unless its first publish succeeds in that window.
6. `npm deprecate @opscogs/octools@0.0.1-bootstrap.0 "bootstrap placeholder"`,
   then set the package to require two-factor authentication and disallow
   tokens.

On PyPI no bootstrap is needed: a pending publisher creates the project on the
first OIDC upload. A pending publisher does not reserve the name, so publish
the first pre-release soon after creating it.
