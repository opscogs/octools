# Upstream requests

Version: **1.2.0** · Date: 2026-10-08

How downstream libraries that track requests under their own decision-record prefix file shared-tool asks against `octools`, and how this repo triages,
delivers and closes them. Any other contributor files a bug or feature request through the plain issue forms and
the flow in [CONTRIBUTING](../../CONTRIBUTING.md). The mechanism is GitHub Issues: a consumer-issued id, one
`ur:` label and a JSONL mirror. The scope test is this package's; see [OCTL-0001](../decisions/OCTL-0001-descriptor-origin.md).

## What qualifies

A request qualifies when the behaviour lives in the `OCTool` descriptor, result envelopes,
pydantic-to-JSON-Schema helpers, conformance validator or MCP/Anthropic converters this
package owns, so no consumer library can fix it on its own. Transport, config, logging,
CLI, telemetry, adapters and field mapping are declined with a comment naming the right
home. Items on the 1.x scope fence in OCTL-0001 are declined the same way
until a new decision record amends the fence. A request names a cost the consumer pays today;
a speculative wish has nothing to accept against and is not filed. Gaps this repo finds in
itself are plain issues cited as `GH-N`, never `UR` ids.

## Ids and states

The consumer allocates `<PREFIX>-UR-NNNN` from its own repo prefix, which is its decision-record
prefix. Numbers are sequential across every upstream the consumer files against, so one consumer's
ids on this repo have gaps, and never reused, including after a withdrawal. The title is the id
followed by the short imperative title the consumer's own record carries:
`DEMO-UR-0042 Add a duration value to column_kinds`. That id, not
the issue number, is the citation key in `CHANGELOG.md`, in commits and in the consumer's archive;
the number only locates the discussion, so ids survive a repo move.

The issue is the canonical record. State is exactly one `ur:` label; the target release is a
milestone (`0.2.0`, `0.3.0`), so wave membership is a milestone, never a label.

| State                | Label          | Moved by             | When                                          |
| -------------------- | -------------- | -------------------- | --------------------------------------------- |
| Filed                | `ur:filed`     | consumer (form)      | the issue is created                          |
| Accepted             | `ur:accepted`  | maintainer           | it passes the scope test                      |
| Planned              | `ur:planned`   | maintainer           | a release milestone is set                    |
| Delivered            | `ur:delivered` | release job          | shipped and cited; the issue stays **open**   |
| Closed `completed`   | unchanged      | consumer or upstream | the consumer raises its floor to that version |
| Closed `not planned` | `ur:declined`  | maintainer           | outside the scope test                        |
| Withdrawn            | `ur:withdrawn` | consumer             | closed `not planned`; the id stays burned     |

Stateless labels: `upstream-request` (type, applied by the form), `ur:blocking` (the impact dropdown
says it blocks a consumer release), `consumer:<package>` (one per consumer, `gh label create`).

## Consumer: check, then file

Fields come from the [issue form](../../.github/ISSUE_TEMPLATE/upstream_request.yml); a `--body-file`
answers the same ones by hand, since `validations.required` binds the renderer and not the API.
The form carries a consumer's request record: the friction (what the gap costs today), the
workaround (or `none`, and why), an acceptance observable from outside — a released version, a
promoted symbol, a documented field — and a size of S, M or L, a rough read for grouping that
no one is held to. State the consumer's declared `octools` range (`octools >= 1.0, < 2`),
not just a floor: the floor is the oldest release carrying every name the consumer uses and the ceiling is always the
next major, per the dependency rule in the descriptor's versioning section, and a triager needs
both to tell whether a request is already satisfied by the newest release.

```sh
# Idempotence: never create without this returning empty
gh issue list --repo opscogs/octools --state all \
  --search "DEMO-UR-0042 in:title" --json number,title
gh issue create --repo opscogs/octools \
  --title "DEMO-UR-0042 Add a duration value to column_kinds" \
  --body-file ur-0042.md --label "upstream-request,ur:filed,consumer:demo_tools"
```

A consumer repo keeps its id allocator, its workaround notes and, once a request closes, one archive
row: id, target, request title, delivering version, adopted floor and closing date. While a
request is open the consumer may keep a tracking entry pointing at the issue, whose status follows
the issue's `ur:` label; the issue stays canonical, and the consumer never edits this repo.

## Maintainer: check, triage, plan, deliver

Check open requests when starting work that might overlap a consumer ask, when planning a
release, and when cutting the changelog:

```sh
gh issue list --repo opscogs/octools --label upstream-request --state open \
  --json number,title,labels,milestone --jq '.[] | [.number, .milestone.title, .title] | @tsv'
```

```sh
# Triage (label edits are idempotent): accept, or decline and close
gh issue edit 12 --repo opscogs/octools --add-label ur:accepted --remove-label ur:filed
gh issue edit 12 --repo opscogs/octools --add-label ur:declined --remove-label ur:filed
gh issue close 12 --repo opscogs/octools --reason "not planned" \
  --comment "Transport territory; file it against the client package."
# Plan into a release
gh issue edit 12 --repo opscogs/octools --add-label ur:planned --remove-label ur:accepted --milestone 0.2.0
```

Delivery is automatic. When a release tag's GitHub release is published, the
`deliver_upstream_requests` CI job runs `scripts/deliver_upstream_requests.py <tag>`: every open
`ur:planned` request in the milestone named after the tag moves to `ur:delivered` and gains the
comment "Delivered in 0.2.0; CHANGELOG cites DEMO-UR-0042. Closes at the consumer floor bump."
It delivers only a request whose id the tag's `CHANGELOG.md` entry cites. A request the entry does not cite, or
one with no id in its title, stays `ur:planned` and appears as a warning on the run; fix the
citation or the milestone and run the script by hand with the same tag. The issue stays open.

The changelog bullet keeps the Linear key of the branch doing the work and names the id in
parentheses at the end of the sentence, per `.cursor/rules/changelog.mdc` — `- OCI-NNN optional
total_count on RecordsEnvelope (DEMO-UR-0042)`. No Linear ticket is opened per request.

## Either role: close on the floor bump

A request closes only when the consumer raises its dependency floor to the delivering version, and
whoever sees that land closes the issue. `gh issue list --label ur:delivered` at a release cut is the
whole check; nothing in CI gates on it.

```sh
gh issue close 12 --repo opscogs/octools --reason completed \
  --comment "demo_tools 0.5.0 pins octools >= 0.2.0."
```

## Mirror

`docs/dev/upstream/requests.jsonl` holds one JSON object per line, one per request, newest last:

```text
{"id": "DEMO-UR-0042", "issue": 12, "consumer": "demo_tools", "title": "Add a duration value to column_kinds", "state": "delivered", "issue_state": "open", "milestone": "0.2.0", "filed": "2026-09-09", "synced": "2026-09-09"}
```

`state` is the suffix of the issue's one `ur:` state label, exactly as set; `issue_state` is
GitHub's `open` or `closed`, so a delivered request whose consumer has raised its floor reads
`"state": "delivered", "issue_state": "closed"`. `milestone` is the target release as set on the
issue. The release that delivered a request is the `CHANGELOG.md` entry citing its id; the floor a
consumer adopts is recorded in that consumer's own repo.

Regenerate with `python scripts/sync_upstream_requests.py` at two moments only — planning a release
and cutting the changelog — and commit it in that same reviewed change; `--markdown` prints a table
on stdout and is never committed. The issue list is the truth; the mirror is for offline review and
for finding the id to cite.

CI runs `sync_upstream_requests.py --check` on every push; it reads the issue list and never
writes. A stale mirror fails a tag build before anything is published, and is a warning on a branch
push, because filing or relabelling an issue changes the list outside git. After the tag's delivery
job moves requests to `ur:delivered`, the next sync lands on `main` in its own reviewed change.
