---
paths:
  - "docs/decisions/**/*.md"
  - "docs/design/**/*.md"
---
<!-- Generated from .cursor/rules/decision-ids-uppercase.mdc by scripts/sync_claude_config.py; edit the source. -->

# Decision IDs are uppercase where a person sees them

Anything named after a decision record — the record itself, spike reports,
risk audits, research notes — uses the **uppercase** ID in its filename and
its H1: `OCTL-0001-descriptor-origin.md`, `# OCTL-0001 descriptor origin`.
The capitals are a visual hint that the file belongs to a numbered decision.

- Filenames: `OCTL-NNNN-kebab-slug.md` (uppercase prefix, lowercase slug).
- H1 and any display text: `OCTL-NNNN`, never `octl-NNNN`.
- Links and URLs may stay lowercase where a tool forces it (web anchors,
  generated slugs); markdown link **targets** must match the real filename,
  so they are uppercase too.
- Never rename an existing record to lowercase to "match" a link; fix the link.
