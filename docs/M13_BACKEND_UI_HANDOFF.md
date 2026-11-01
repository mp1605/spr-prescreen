# M13 backend handoff for the UI chat

Frontend source and built assets were not edited or rebuilt during this work. All 62
previous frontend/static file hashes remained unchanged at verification. UI editing can
continue independently. Existing request/response shapes and M12 scorecard routes remain
compatible; new development data have a separate endpoint.

Project: `/Users/mpatel/Projects/spr-prescreen`.
Updated isolated backend: `http://127.0.0.1:8520`.
Active detector registry: `LOE2-guide-v5-admin`; semantic bands 0.84 / 0.86, AI off.
Existing services on 8501/8502 were not restarted. Restart those when deliberately ready
to load the new backend/configuration. No frontend rebuild is needed for the backend changes.

## New endpoint

`GET /api/evaluation/development/latest`

The response contains:

```text
milestone: M13-development
split: dev
tuned_on_this_split: true
unseen_validation: false
holdout_reused: false
report: existing EvaluationReport contract
disclaimer: Pre-screen only — a reviewer makes the release decision.
release_decision: NOT_MADE_BY_TOOL
```

The measured report covers all 60 development cases. It is not a new holdout result.
An absent report returns 404; an invalid/wrong-split report returns 503. Reading the
endpoint does not rescan documents, access keys or invoke a model.

The existing `/api/evaluation/scorecard/dev` and `/holdout` continue to show the original
frozen M12 evaluation. Do not replace their historical values with M13 development values
or combine the new dev values with old holdout values as a new blind score.

The current frontend has not been wired to this new endpoint; this is an additive backend
integration point for the UI chat. Existing screening/review uses the new active rules
after backend restart. Old results remain immutable; an explicit rescan creates new results.

## Current development measurements

68/74 triggers matched (91.9%); List 1 23/23 (100%); paper-color accuracy 49/60 (81.7%);
86 unmatched passages; 0/15 green papers flagged; 0/6 declared decoys flagged. These
measurements were used to develop/select the detector/configuration changes and do not
establish performance on unseen papers. Six globally missed triggers remain, and ten
List 2 triggers lack a matching List 2 item (some cross-list triggers match List 1 only).

Artifacts: `reports/m13/final-dev.json`, `final-dev.md`, `publication.json`,
`preservation.json`, `pytest-final.txt`, `offline-smoke.json` and `M13_REPORT.md`.

The parser writes version 3, excludes numbered fictional-source notes, and still accepts
historical version-2 parse records for existing review. Old version-2 caches are not reused
for a fresh version-3 parse. Evidence coordinates and original-layout review contracts
are unchanged. No new item IDs, official wording or release-decision semantics were added.
