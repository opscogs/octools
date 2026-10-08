# Architecture decision records

This directory holds architecture decision records (ADRs) for octools, written
in the [MADR 4.0](https://adr.github.io/madr/) format. The
[decision log](decision-log.md) lists every ADR with its current status and
version, plus a dated history of changes. New records start from the
[template](adr-template.md).

- File names follow `OCTL-NNNN-kebab-case-title.md`, numbered in order of
  creation. The H1 is `# OCTL-NNNN title`. Numbers are never reused; a gap in
  the sequence is a number whose record was withdrawn before it merged.
- Each record starts with YAML front matter giving `status` (`proposed`,
  `accepted`, `rejected`, `deprecated`, or `superseded by OCTL-NNNN`),
  `version`, `date` (the date of the last change), and `decision-makers`.
- A record states what holds now, in the present tense. Alternatives live
  only in Considered Options and Pros and Cons of the Options. Changing an
  accepted decision rewrites the record to state what now holds and bumps its
  version; replacing it outright adds a new record and marks the old one
  `superseded by OCTL-NNNN`.
- The octools release and `SPEC_VERSION` a decision ships in go under More
  Information; the front-matter `version` is the record's own version.

These records are engineering notes and are not published to the MkDocs site
(`docs_dir` is `docs/site`). Design notes and working documents belong in
`docs/design/`.

## Versioning

Each ADR has a [semantic version](https://semver.org/) in its front matter.
New records start at `0.1.0`. Bump once per commit that changes a record,
compared with the version on `main`.

| Change                                                                | Bump  | Example         |
| --------------------------------------------------------------------- | ----- | --------------- |
| While proposed: new or changed content                                | minor | `0.1.0 → 0.2.0` |
| While proposed: wording, links or formatting                          | patch | `0.2.0 → 0.2.1` |
| Status changes to accepted                                            | major | `0.2.1 → 1.0.0` |
| After acceptance: the decision or an invariant is removed or narrowed | major | `1.0.0 → 2.0.0` |
| After acceptance: an additive change                                  | minor | `1.0.0 → 1.1.0` |
| After acceptance: wording, links or formatting                        | patch | `1.1.0 → 1.1.1` |
| Status changes to rejected, deprecated, or superseded                 | minor | `1.1.1 → 1.2.0` |

Versions below `1.0.0` mean the decision is still in draft. Accepting a record
is the only way it reaches `1.0.0`.

## Changing a record

1. Edit the ADR and update `version` and `date` in its front matter.
2. Update the ADR's row under **Current decisions** in the
   [decision log](decision-log.md).
3. Add a row at the top of the log's **History** table.
