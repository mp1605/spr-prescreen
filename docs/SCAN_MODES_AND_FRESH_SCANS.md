# Scan modes and fresh-scan behavior

The canonical project and owned QA app at http://127.0.0.1:8520 now have a Scan mode dropdown beside file selection. Refresh Batch & Queue. Other running backend instances must restart to load the new modes.

| Dropdown mode | Full-document baseline | Ollama input |
| --- | --- | --- |
| Python scanner — no Ollama | Rules + local semantic matching on all readable extracted text | No generation request |
| Selective AI | Same full baseline | Current flagged passages plus one adjacent segment on each side, constrained to the same document part and section |
| Full AI | Same full baseline | All readable extracted source segments |

“No Ollama” is deliberately not labeled “no machine learning”: the existing local BGE semantic model remains active. List 1 then List 2 always run. AI can add source-verified findings or supported specificity, and cannot erase or downgrade baseline findings. Human accept/override remains separate and never constitutes automatic release.

The dropdown is visible before files are chosen. It follows the admin default until explicitly changed, then the selected mode is pinned in the new batch. Start/Cancel and file add/remove remain functional. Admin controls still govern the configured local model, context and deadline. AI-on modes require that local model to be available and valid; they do not silently fall back to the Python-only mode.

## Actual AI coverage

The new per-batch scope is stored in ai_settings.scope and each result’s ai.scope. The result records total_source_segments, source_segments, source_segment_ids, generation_attempted, state, prompt/configuration/pipeline digests and elapsed time. The paper review panel shows scope, selected segment coverage and whether generation was attempted. Legacy AI records leave the new generation-attempt field unknown rather than claiming no request occurred.

Selective mode with zero baseline candidates records ai_state=skipped, zero selected segments and no generation request. It retains the baseline result and explicitly says no full-paper LLM review occurred. This mode cannot discover a completely isolated miss outside its selected passages/context. Quote verification is limited to the source actually sent to the model; quotations from unsubmitted parts are rejected.

Full mode remains one bounded request per paper. It sends extracted text—not PDF/DOCX binary, images, original layout or hidden content the parser did not extract. Noise exclusions remain. Over 512 selected source segments or an over-budget context produces an explicit source/context-budget error and incomplete status with baseline findings retained. It does not silently trim the paper or change Full AI to Selective AI. No chunked full-document LLM implementation is claimed.

## Answer keys, caches and old results

The upload scanner does not look up answer keys, expected colors, seeded case IDs, filenames or source hashes to choose results. Exposed papers and keys were used for evaluation and authorized development tuning of general detectors. This means the known 80-paper accuracy figures are tuned development results, not independent validation.

Each new uploaded-and-started batch runs current List 1 and List 2 detection, semantic matching and source-specific color decisions. Identical bytes may reuse verified parsed text and semantic vectors, keyed by source hash, parser/model/text identity. These are source representations, not cached final classifications or answer-key predictions. Changed bytes under the same filename receive a different source hash and are screened from that new input. Full AI makes a new generation request for each new scan, subject to availability/budgets/deadlines; Selective AI may skip when it selects no source.

Opening an existing paper or the original Scorecard displays saved historical results. It does not rescan on page view. New upload/Start or the explicit Rescan action creates a new run; previous results and review decisions stay immutable. The existing Rescan action continues to use current admin AI defaults unless its API caller supplies a different future workflow; the upload dropdown applies to the next newly uploaded batch.

## API / UI handoff

POST /api/batches?ai_mode=off|selective|full uses the explicit mode. The legacy on alias means Full AI; default or omitted keeps the existing admin-default behavior. Multipart input still contains files. The returned batch records enabled and scope in ai_settings. Retries retain that snapshot.

AISettings.scope defaults to full for backward compatibility. PaperResult.ai_state and AIInfo.state now also accept skipped. Existing off/ran/timeout/error values remain valid. AIInfo’s coverage fields have backward-compatible defaults; generation_attempted is null for unknown legacy records and explicit true/false in new records. JSON and CSV ai_configuration_json exports carry these fields. Normal review/export contracts otherwise stay unchanged.

Frontend: components/BatchSelection.tsx implements the dropdown, logic/scanModes.ts defines modes/labels, UploadBatch.tsx sends the selected API value, BatchSummary.tsx displays the stored mode, and AISummary.tsx shows actual AI coverage and generation state. Carry these contracts into the separately developed UI; its isolated directory was not edited.

## Verification and limits

- Main backend suite: 648 passed, five optional real-Ollama checks skipped. A follow-up 14-test batch/freshness suite passed; it includes one new Full-AI cache test not collected in that main run. 649 distinct tests were verified across the two runs.
- Full and Selective mode tests inspect actual request payloads through a deterministic protocol provider: all five source atoms versus the three selected atoms; no-candidate skip; rejected out-of-scope quote; section boundaries; and full-context refusal without fallback.
- Freshness tests confirm that both lists run again on a parse-cache hit, that changed bytes under an unchanged filename change the result, and that normal uploads make no reads of reports/key folders or gold answers. A repeated identical-source Full AI test makes two provider calls and uses the second response rather than reusing the first AI result.
- Frontend: 29 render/metadata assertions, production build, ESLint and formatting checks passed. Strict mypy passed on 114 files; Ruff passed.
- In-app browser verified the three dropdown options and their explanations; screenshot saved. Existing mechanical mixed-upload, Add/Remove, Start/Cancel checks are preserved from the preceding implementation.
- Actual offline format workflow passed: mixed PDF/DOCX upload, rules/semantic screening, review, original-layout Word preview, rotated PDF, highlighted exports and CSV/JSON reports. Zero unexpected blocked network calls. This is not a physical Wi-Fi-off certificate.
- All 92 original M12 evidence artifacts remain unchanged; official rules and the scorer were not modified in this change. No new sponsor accuracy evaluation was performed. The new modes were not benchmarked across 80 papers using real Ollama; five live model checks remain opt-in.
- Source/build snapshots are preserved under reports/scan-modes, as recorded in validation.json. No replacement offline distribution ZIP was built.
