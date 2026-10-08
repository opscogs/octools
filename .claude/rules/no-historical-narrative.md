<!-- Generated from .cursor/rules/no-historical-narrative.mdc by scripts/sync_claude_config.py; edit the source. -->

# No historical narrative

Every document is written for a reader who arrives **today** and needs to use
what exists **now**. The path the code took to get here is not part of that.
Cut it.

## What this bans

- **Prior drafts and superseded numbers.** "An earlier measurement derived X",
  "the first draft used Y", "this was originally Z". State the value that
  holds and why it holds.
- **Order-of-operations accounts.** "We measured, then trimmed, then
  re-derived." A reader cannot act on the sequence. State the outcome.
- **What another repo used to do.** Especially an experiment that was
  withdrawn, a record that was deleted, or a branch that was squashed away.
  **Never cite an ID a reader cannot open.** If it is not on a published
  `main`, it does not exist and must not be named.
- **Mistakes, reversals and things considered.** Approaches tried and
  abandoned, bugs found during development, arguments that were had. A
  rejected alternative is worth one clause only when a reader would otherwise
  reach for it — and then it is stated as a rule ("use `X`, not `Y`, because
  `Y` does Z"), never as a story.
- **Provenance framing** — "ported from", "extracted from", "inherited",
  "carried over" — where the reader gains nothing. Where the origin is a real
  compatibility fact a caller must know, that is an interface note, not
  history.
- **Source-file pointers.** Do not list `python/src/…` paths, module names used as
  file maps, or a "Relevant code" section. Those references die on rename
  and refactor. Name the behaviour, the API, the table, or another ADR.
  `git grep` finds the code.
- **Disposable implementation notes.** Standing records (ADRs, site docs)
  do not link to working notes that are deleted after the work ships:
  handoffs, `implementation-notes`, scratch plans. Those notes point at the
  ADR. The ADR never points the other way, or the link rots the day the note
  is removed. `docs/design/` holds both kinds: a design doc kept as a
  permanent reference may be cited; a working note there may not. A note
  that is meant to outlive its work says so under its H1.

## What stays

- **The decision and its standing rationale**, in the present tense. *Why the
  cap is 1,750* is documentation. *Why it is not the number we first wrote* is
  not.
- **Consequences a reader must act on**: breaking changes, migration steps,
  version floors, deprecations. These are forward-looking even when they refer
  to the past.
- **Discretionary choices** where a standard is silent, stated as what the
  implementation does and what the caller therefore observes.

## The test

> Delete the sentence. Can a reader still do their job, and would they make
> the same choice? Then it was narrative — leave it deleted.

## Decision records are not diaries

An ADR in `docs/decisions/` (MADR 4.0, `OCTL-NNNN-*.md`) states a decision,
its rationale, and its scope. MADR's Considered Options and Pros and Cons are
the one sanctioned place for alternatives. A record does not narrate the
discussion, the sequence of drafts, or the state of any repo when it was
written. A resolved open question becomes part of the decision, stated in
the present tense. Changing a decision means **rewriting the record to state
what now holds** and bumping its front-matter `version` (see
`decision-versioning`), not appending an account of the change; the decision
log's History table and `git log` hold the history. Replacing a record with a
new one sets `status: superseded by OCTL-NNNN` on the old one. An ADR cites
other ADRs, the API, tables, and published site docs — not files that expire.

## In code

The same applies to docstrings and comments. Describe the behaviour, not its
revision history — that is what `git log` is for. A comment beside a constant
gives the reason the value holds, not the values it used to have. A comment
does not cite another file's path to "help the reader find it."
