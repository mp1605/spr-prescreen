# M11 backend integration for the UI agent

Historical M11 contract. M12 now loads authorized stored reports and reports complete
status when available; see `M12_EVALUATION.md` for the current extension. The deferred
behavior below still applies to workspaces without evaluation artifacts.

Backend portion prepared 1 November 2026. The canonical project is
`/Users/mpatel/Projects/spr-prescreen`. The frontend is now integrated at `/items` and
`/scorecard`, including generated local assets. This supplements the detailed SPR UI handoff; it does not replace
`MASTER_PROMPT.md` or the user's direct constraints.

## Implemented scope

- Read-only Review by Item index and paginated finding navigation, across stored browser
  batches or explicitly selected runs.
- Original raw evidence, source locations, per-item assessments, engine provenance,
  historical rules versions and incompleteness retained in every finding row.
- Existing accept/override/inspect/undo endpoints remain the only decision write path.
  They retain reviewer attribution, optimistic revisions, immutable results and audit history.
- Both evaluation split status endpoints truthfully return deferred with no report.
- Queue review progress now replays each batch's audit log once per request, rather than
  once per paper. No scanning engine, detector, color threshold or AI setting changed.

The new screen components/routes/navigation are implemented. Health metadata is M11.
Older already-running services require a restart to load the new backend routes.

## Review by Item index

`GET /api/review/items`

Optional repeated `run_id` query parameters select a scope. Omit the parameter to use all
browser batches. At most 100 run IDs can be passed explicitly. Duplicate IDs are deduplicated;
unknown or invalid IDs are errors, never a fallback to another scope.

Example request shape with an operator-selected valid run ID:

```text
GET /api/review/items?run_id=web-{32 hexadecimal characters}
```

The braces in this example describe the ID format; they are not literal valid IDs.

Response:

- `scope.run_ids`: selected runs, newest first, with run ID as a deterministic tie-breaker.
- `scope.snapshot`: opaque SHA-256 snapshot token covering registry, run records and review
  revisions. Do not derive or modify this token in the client.
- `scope.completed_papers`: done entries with valid results, including flagless papers.
- `scope.unfinished_entries`: queued/parsing/list1/list2/ai entries excluded from item findings.
- `scope.unavailable_entries`: terminal failed/rejected/cancelled entries or done entries
  without results, also excluded from item findings.
- `scope.incomplete_papers`: completed results with incomplete pages or reasons.
- `scope.unique_findings`: raw findings counted once per upload.
- `items`: every official item, in List 1 then List 2 order, including items with zero findings.
  There are 39 items; List 1 has no item 2.
- `count_convention`: explanatory text for overlapping item counts and review semantics.

Each item contains `item_id`, `list`, `text`, `source_pages`, `findings`, `papers`, `red`,
`yellow`, `pending`, `accepted` and `overridden`.

`papers` counts upload instances, not unique source hashes. Identical uploads retain
independent review state. A multi-item finding appears under every named item, so summing
item counts can exceed unique findings. Color counts are the finding's raw passage
priority, not an independent color determination for every item. Use
`finding.assessment.items` for item-level specific/possible evidence.

A reviewer decision applies to the whole finding. Accepting a multi-item finding updates
its state under every one of its named items. It must not produce several independent
decisions for that same finding.

## Paginated findings for one item

`GET /api/review/items/{item_id}`

| Query parameter | Behavior |
| --- | --- |
| run_id | Optional repeated selected-run scope, as above |
| review_status | all, pending or reviewed; default all |
| color | all, red or yellow; default all; this is the raw finding color |
| search | Case-insensitive filename substring, at most 200 characters |
| offset | Nonnegative row offset, default 0 |
| limit | 1 through 100, default 25 |
| if_snapshot | Optional token from the index or previous page for the same scope |

Response:

- `scope`: same scope metadata and token as the index.
- `item`: unfiltered summary for this item within that run scope.
- `total`: number of findings after color/review/filename filters.
- `offset`, `limit`, `has_more`, `entries`: pagination state and matching rows.
- `release_decision`: always `NOT_MADE_BY_TOOL`.

Rows are ordered newest batch first, then case-insensitive filename and upload ID. Findings
within an upload retain their stored order. Empty items and offsets beyond the last row
return an empty page with `has_more: false`; they do not create fabricated findings.

Each row contains:

| Field | Meaning |
| --- | --- |
| run_id and entry_id | Durable upload identity |
| file_name and file_type | Document label and native format |
| paper_color | Raw overall screening priority |
| rules_version | Version recorded by that historical result, not the current registry version |
| incomplete_reasons and incomplete_pages | Manual inspection requirements |
| review_revision | Current revision for writes to that upload's decisions endpoint |
| decision | Current accept/override event for this finding, or null |
| finding | Unmodified complete Finding schema, including evidence/assessment/provenance |
| review_url | Existing paper review route |
| decisions_url | Existing per-upload GET/POST decisions endpoint |

The paper-review screen accepts `?finding=<finding_id>` and selects that stored finding.
The item screen also provides an integrated original-layout evidence panel.

Use the token while paging. If the scope's results, registry or decision revisions have
changed, `if_snapshot` yields HTTP 409 with instructions to refresh and restart pagination.
This prevents silently skipping rows after a pending finding becomes reviewed. After any
decision, invalidate the item index, item pages, paper decisions and batch progress queries;
fetch a new index/token, then continue. Current offset pagination is not a frozen server-side
session and does not remain valid across mutations.

## Sequential accept override and undo

Use each row's `decisions_url`. Existing request schemas remain unchanged:

```json
{
  "action": "accept",
  "revision": 0,
  "reviewer": "Reviewer display name",
  "finding_id": "the exact selected finding ID"
}
```

The revision shown is an example only. Send the row's current revision, then use the server
response before another write to that upload. Override uses `action: override` and optional
`reason`. Undo uses the existing event target and reviewer rules; load the complete current
ReviewState through `decisions_url` to determine the eligible event. A list row is not the
entire undo stack. Inspection is a paper action, not an item-specific decision.

Preserve optimistic rollback and visibly handle HTTP 409. A reviewer name is required.
Display-name attribution does not create authenticated reviewer identity. A decision does
not edit raw findings, recolor highlights, repair an incomplete source or determine release.

No new bulk write endpoint exists. Sequential review should save one deliberate action at
a time and let the reviewer navigate the next pending finding. Maintain keyboard controls
and show the source before a reviewer acts. Do not auto-accept on page load or selection.

## Error behavior and network scope

Invalid query values return HTTP 422. An unknown official item or run returns 404. A stale
snapshot returns 409. Damaged stored results return a visible error rather than an empty
queue. API responses use no-store caching and the existing local-only security headers.

Index/page reads use completed results and separate review audits only. They do not open
source originals or parsed document files, rescan papers, discover evaluation datasets,
load answer keys, run models or make external network requests. Actual source rendering
continues through the existing paper/document/page/layout endpoints.

## Scorecard status and the blind-evaluation boundary

`GET /api/evaluation/scorecard/dev`

`GET /api/evaluation/scorecard/holdout`

Both return:

```json
{
  "split": "dev",
  "state": "deferred",
  "sponsor_material_access": false,
  "sponsor_accuracy_measured": false,
  "report": null,
  "message": "Sponsor evaluation is deferred until implementation is complete and separately authorized. No scorecard measurements are available.",
  "disclaimer": "Pre-screen only — a reviewer makes the release decision.",
  "release_decision": "NOT_MADE_BY_TOOL"
}
```

The holdout endpoint returns `split: holdout`; other fields have the same deferred meaning.
Show Not measured/Not performed, not zero recall, zero errors, perfect accuracy or an empty
confusion matrix that resembles actual measurements. Tab selection must not initiate a run
or consume a holdout claim. There is no evaluation-run, key-upload or report-import API in
this implementation. Unknown POSTs remain rejected by the existing application routing.

The OpenAPI schema includes the existing EvaluationReport contract for future integration:
trigger/list-specific recall, item Jaccard, flag/paper color accuracy, confusion matrix,
false alarms, reference-paper false alarms, decoy hits, incomplete count, AI-on/off timing,
rules versions, cases with missed quotes and matching/cost assumptions. The status endpoint
currently returns no such measured report. The later authorized evaluation stage still
needs report persistence/loading and execution integration. Do not fill the screen with
invented example metrics or inspect sponsor material to create a preview.

## Files and ownership

New backend files:

- `backend/core/item_review_models.py`: item index, scope, page and row contracts.
- `backend/core/item_review.py`: read-only aggregation, filters, pagination and snapshot checks.
- `backend/api/items.py`: item-navigation routes and bounded query validation.
- `backend/api/evaluation.py`: deferred read-only scorecard status routes.

Existing backend changes:

- `backend/core/review_store.py`: shared single-entry replay and one-read per-batch replay.
- `backend/api/batches.py`: queue uses the per-batch replay.
- `backend/app.py`: registers the new API routers.

Tests are in `tests/integration/test_items.py` and
`tests/integration/test_scorecard_status.py`. They use official-phrase formatting and
in-memory counting/state contracts, not sponsor papers. A generated OpenAPI JSON accompanies
the handoff. It is produced from an isolated application root with no user runs or credentials.

FastAPI's SPA fallback includes `/items` and `/scorecard`; direct URL refresh is covered
by integration tests. See `docs/M11_UI.md` for frontend implementation locations.

## Validation boundary

See `reports/M11_REPORT.md` for the implemented frontend, browser checks, measured
performance and accessibility audit method. Separately authorized sponsor evaluation is
M12. M10 physical disconnection and second-Mac acceptance remain unverified.
