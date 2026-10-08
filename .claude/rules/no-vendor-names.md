<!-- Generated from .cursor/rules/no-vendor-names.mdc by scripts/sync_claude_config.py; edit the source. -->

# No vendor names

`octools` is a generic OpsCogs package. It never names a specific vendor
or product — not the platform a consuming library wraps, its API, its
appliance or clustering terms, nor any other external vendor — anywhere:
code, docstrings, tests, docs, examples, `.cspell` words, or rule files. Vendor-specific facts belong in the repo of the
library that adopts `octools`, not here.

Examples stay in neutral vocabulary:

- runtime prefix: `demo_`
- access target: `"cluster"`
- meta key: `min_api_version`
- tool name: `cluster_info`

Before adding a name, path, or sample value, check it is not a real
vendor or product term. If a vendor word is genuinely unavoidable (e.g.
quoting an external source), replace it with a neutral placeholder such
as `<platform>` and say so in the surrounding text.

There is no exemption. The whole repository is public, so `docs/design/`,
`docs/dev/`, `docs/decisions/`, `docs/site/`, `README.md`, `python/src/`, `python/tests/`, `spec/` and `typescript/`
all stay free of vendor names and of the names of private sibling repositories.
