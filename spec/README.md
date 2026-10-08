# octools spec

Version: **1.0.0** · Date: 2026-10-08

`spec/` is the language-neutral contract of `octools`: the wire format of
the descriptor and the result envelopes, the closed vocabularies and their
fallbacks, and golden cases for every language-neutral operation in the
public API. Every implementation passes all of it; none skips a case.

## Layout

| Path                               | What it holds                                                                                                                                | Edited by         |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| `vocabulary.json`                  | `spec_version`, every closed vocabulary with its values and fallback, and the shared constants (name patterns, sentence limits, strict sets) | generated         |
| `schema/*.schema.json`             | JSON Schema 2020-12 of the descriptor (every field but the callable), the three envelopes, a finding and a listing row                       | generated         |
| `fixtures/<operation>/<case>.json` | One golden case per file for one operation                                                                                                   | by hand, reviewed |

`vocabulary.json` and `schema/` are generated from the Python models by
`scripts/sync_spec.py`, never edited by hand. Run it after changing a model
or a constant; `python scripts/sync_spec.py --check` lists stale, missing
and extra files and exits 1 without writing. The test suite runs the same
check.

## Fixture format

```json
{
  "description": "What the case shows, in one sentence.",
  "input": { "tool": { "name": "cluster_info", "...": "..." } },
  "expected": []
}
```

The directory names the operation; `input` holds its arguments as JSON and
`expected` the JSON value the operation produces. Conventions:

- **Tools** are plain descriptor objects: every descriptor field except the
  callable, which the runner supplies (`descriptor.schema.json`).
- **Providers** are `"tools": [...]`, a stable listing, or
  `"listings": [[...], [...]]`, where call `n` of `all_tools()` returns
  `listings[n]` and later calls the last one. An item that is not an object
  is a foreign, non-tool item.
- **Findings** compare as `{"rule", "tool", "path"}`. `message` is for a
  person and is not part of the contract.
- **Envelopes** compare as their serialized JSON (optional fields left out
  when unset, `resumable` only when `truncated` is true).
- **Errors** are data: `{"error": "<code>"}`.

| Error code           | Raised when                                                    |
| -------------------- | -------------------------------------------------------------- |
| `invalid_descriptor` | a descriptor fails construction                                |
| `invalid_name`       | a converted name, prefix included, breaks the target's pattern |
| `invalid_envelope`   | an envelope fails parsing, strict or tolerant                  |
| `invalid_style`      | a listing style is outside `LISTING_STYLES`                    |

Operations and their `input` keys:

| Operation                                 | `input`                                                                  | `expected`                      |
| ----------------------------------------- | ------------------------------------------------------------------------ | ------------------------------- |
| `OCTool`                                  | `tool`                                                                   | the descriptor, defaults filled |
| `read_envelope`                           | `model` (`records`, `tabular`, `artifact`), `data` (object or JSON text) | the envelope, read tolerantly   |
| `validate_envelope`                       | `model`, `data`                                                          | the envelope, parsed strictly   |
| `validate_tabular`                        | `envelope`                                                               | findings                        |
| `validate_tool`                           | `tool`, optional `unchecked` (fields set after construction)             | findings                        |
| `validate_provider`, `check_tool_listing` | `tools` or `listings`                                                    | findings                        |
| `merge_providers`                         | `providers`, each `{"tools": [...]}`                                     | the merged listing's names      |
| `to_mcp_tool`, `to_anthropic_tool`        | `tool`, optional `name_prefix`                                           | the converted tool              |
| `strict_clean`                            | `schema`                                                                 | findings                        |
| `strip_keys`                              | `schema`, optional `keys`, `prefixes`                                    | the schema                      |
| `strip_titles`, `close_objects`           | `schema`                                                                 | the schema                      |
| `count_sentences`                         | `text`                                                                   | an integer                      |
| `summarize_tool`                          | `tool`                                                                   | the listing row                 |
| `summarize_provider`                      | `tools`, optional `access`                                               | listing rows                    |
| `render_listing`                          | `tools`, optional `style`, `access`, `pretty`                            | the rendered text               |
| `render_markdown_table`                   | `rows`, `columns`                                                        | the rendered text               |

A runner for each operation lives in each implementation's test suite.
A fixture directory with no runner fails the suite.
