# Scanner v6: development accuracy and verification

Published: LOE2-guide-v6-admin · 2026-11-01T08:40:25.878149+00:00

All 80 sponsor papers (60 DOCX, 20 PDF) were actually rescanned using the published rules. All source/key hashes match the original evaluation. All 80 are now exposed development data. This is not an independent or blind validation.

| Measurement | Before (v5, all 80) | After (v6, all 80) | After count / definition |
| --- | ---: | ---: | --- |
| Trigger recall | 80.8% | 100.0% | 99/99 |
| List 1 recall | 90.3% | 100.0% | 31/31 |
| List 2 recall | 72.2% | 93.7% | 74/79 |
| Paper color accuracy | 75.0% | 98.8% | 79/80 |
| Matched flag color accuracy | 70.0% | 90.9% | 90/99 |
| Item-set micro Jaccard | 72.1% | 68.5% | Full item labels, not just one overlapping ID |
| Unmatched predicted passages | 141 | 184 | Lower is better |
| Green papers flagged | 0/20 | 0/20 | All 20 stayed green |
| Decoys flagged | 0/6 | 0/6 | Six explicit decoys only |

**This is not 99–100% overall accuracy or precision.** Recall means finding seeded passages. A passage counts as detected when source matching passes and at least one official item ID agrees. Other item labels can still be missing or excessive; item-set agreement is 68.5%.

The unchanged scorer counts 184 unmatched predicted passages, up from 141. Under that strict seeded-passage definition, precision is 35.0% (99 / (99 + 184)), not above 90%. Some unmatched passages may discuss real official topics, but they remain counted as false alarms under this evaluator. No label, denominator, matching threshold, crosswalk or scoring logic was changed to hide them.

One paper-color disagreement remains: SPR-Test-067 is yellow rather than the key’s red. The text describes hypersonic capabilities and possible warning limitations without the specificity required for automatic red. Nine matched passage colors differ from the keys. These are documented in the detailed report; they were not forced red to match expected answers.

What changed:

- Added contextual paraphrases for the existing official items: procurement confidentiality, operational personnel details, biological research, military dependencies, readiness shortfalls, own-unit techniques, cyberattack wording, and PFAS response actions.
- PFAS response references can use an explicit PFAS topic elsewhere in the same document part; excluded educational/source notes cannot supply that context. A generic response plan alone is insufficient.
- Added literal measurement, performance, dependency and disclosure facts. Evidence retains exact source coordinates; semantic similarity alone still cannot establish a clear List 2 match.
- Preserved hypothetical and negated-disclosure gates; distinguished reported inability and explicit schedules from speculative benefits. Generic standard procedures remain possible.
- Preferred substantive body evidence over a redundant short topic heading where the same item is independently present in the following body segment. List 1 evidence is retained.

Policy and workflow:

- Official item IDs, wording, categories, examples and list ordering are unchanged. List 1 then List 2 ran on every paper; List 1 never short-circuits List 2.
- Detector data was published through Draft → Validate → explicit-upload impact preview → Publish. Preview compared all 80 supplied sources. No authentication/role protection was removed.
- The preview compares detector versions under the revised source code. The pre-change v5 full regression remains separately preserved for the actual before/after comparison.
- 62 frontend/static file hashes are unchanged. No UI files were edited. The QA app at http://127.0.0.1:8520 reports LOE2-guide-v6-admin. Existing results remain immutable; newly scanned papers use the revised scanner.
- All 92 original M12 evidence artifacts and the one-shot holdout ledger remain unchanged. The existing archived scorecard continues to show that original evaluation; it was not relabeled as a v6 result.
- The v5 development reports and the all-80 pre-change regression remain preserved.
- Runtime screening does not load answer keys, expected colors, case-ID branches, filename rules, source-hash rules or gold quotations. Evaluation-only scripts load keys separately.

Verification:

- 625 tests passed; five opt-in live-Ollama tests skipped. Added atomic source/uncertainty/context tests, not generated evaluation papers.
- Strict mypy passed on 112 backend files; Ruff passed.
- Offline workflow smoke passed: two mechanical PDF/DOCX inputs, rules plus local semantic screening, human review, original-layout Word preview, rotated-PDF preview, highlighted downloads and CSV/JSON exports. Zero unexpected blocked network attempts.
- AI was off and there were zero Ollama calls in the all-80 measurement.
- Final all-80 screening loop took about 5.3 seconds using 80 warm source-vector cache hits. This excludes source/key preflight, model startup and uncached embedding generation. It is not a fresh-install or cold-processing benchmark.
- Native models are present; the app reports its Python airlock installed. Wi-Fi-off and second-machine installation are not certified by this run. The old M10 USB bundle was not rebuilt and predates these changes.

Remaining work:

- Reduce excess flags and item-label errors without hiding required official-topic candidates.
- Validate on a new unseen, independently labeled dataset. The original 80 cannot support another blind claim.
- Obtain a separate cleared/reference corpus; its false-alarm rate is unmeasured, not zero.
- Rebuild the offline distribution after the parallel UI work is integrated, then perform physical disconnected and second-machine checks.

Evidence files in the canonical project: reports/accuracy-v2/final-report.json, final-report.md, final-predictions.json, final-validation.json, publication.json, pytest-final.txt and offline-smoke.json. Source snapshots and each development iteration are preserved alongside them.
