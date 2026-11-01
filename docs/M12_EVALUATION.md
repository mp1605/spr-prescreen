# M12 evaluation integration

The user authorized sponsor access on 1 November 2026 after M11 implementation. Scanner
configuration remains frozen and uses only official references. This separate evaluator
does not train, calibrate, harvest exemplars or pass keys to scanning engines.

## Implementation locations

- `backend/eval/dataset.py`: explicit canonical paper/key inventory and the reviewed
  answer-reference crosswalk. Duplicate suffixed keys and INDEX.csv are excluded.
- `backend/eval/frozen.py`: compares scanner/core/security, policy, settings and authority
  hashes to the pre-evaluation M11 manifest before and after execution.
- `backend/eval/runner.py`: private parse/vector cache, dev E1 baseline, dev final pass,
  one-shot holdout claim, durable predictions and measured scores. AI remains off.
- `backend/eval/parse_keys.py`: evaluation-only decoy grammar now permits explanations
  after the primary closing quotation. Scanner extraction/detection is unchanged.
- `backend/eval/archive.py`: validates completed stored reports and holdout provenance;
  it does not open paper/key sources or run inference.
- `backend/api/evaluation.py`: `/api/evaluation/scorecard/dev` and `/holdout` now expose
  those archived reports. Invalid artifacts fail visibly; absent artifacts remain deferred.
- `frontend/src/pages/Scorecard.tsx`: working tab/refresh/download flows. The report
  renderer shows real metrics, confusion matrix, misses, decoys, unmatched passages,
  failure notes and timing. Missing cleared-paper observations are labeled Not measured.
- `scripts/report_m12.py`: generates summary and detailed reports from saved evidence;
  it never reruns screening. `scripts/evaluate_m12.py` requires explicit source paths
  and the authorization flag and refuses already-claimed output.

## Artifacts

`reports/evaluation/` contains private `authorization.json`, `dataset.json`, `gold.jsonl`,
`rule-reference-crosswalk.json`, `dev-rules-only.json`, `dev.json`, `holdout.json`,
`combined.json`, per-paper predictions, `timing.json`, `gold-source-alignment.json`,
`item-coverage.json` and the completed `holdout-claim.json`. The holdout claim is exclusive;
it cannot be silently reset or replaced by another run.

`reports/M12_EVALUATION_REPORT.md` explains results and limits.
`reports/TEST_REPORT.md` quotes every global and list-specific miss and every unmatched
passage/declared decoy hit. `reports/M12-validation.json` records checks and provenance.

Read results without inference:

```sh
.venv/bin/python -m backend.eval status
.venv/bin/python -m scripts.report_m12
```

Do not repeat the holdout, delete its ledger, or tune against its results. A future
improvement cycle must preserve this frozen result and be explicitly scoped separately.
The software tests passed; accuracy targets failed. The UI and reports must preserve
that distinction. No release decision is made by the tool.
