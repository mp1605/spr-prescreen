# Batch selection and per-batch Ollama choice

Implemented in the canonical project and deployed to the owned QA workspace on port 8520. Refresh Batch & Queue to load the new built frontend. Other backend instances must be restarted before using the new per-batch API option.

Selecting or dropping files now keeps them in the browser until Start scan. Add files and Choose folder append to the selection. Remove deletes an individual selection; Cancel clears an unstarted selection. Files remain editable before Start. Unsupported, oversized and excluded key/metadata files are listed with reasons and block Start until removed. The limits remain 100 files, 25 MiB each.

The selection includes Use local LLM (Ollama) for this batch. It initially follows the admin default; an explicit checkbox choice overrides that default for this batch. Rules and local semantic screening always run. Model, context and timeout configuration remain admin-managed. Opting in checks the configured cached local model, supported context and any existing pinned digest; it pins the verified model in the batch record without changing global settings. Unavailable or incompatible AI rejects the requested batch before storing files or starting any scan; it never silently falls back to AI off.

After Start, selection edits are locked during the upload. Cancel during that upload remembers the cancellation request, waits for the response identifying the new batch, then calls the existing cancellation endpoint. This does not abort the transfer instantly. Completed results remain; queued/in-progress work uses the existing cooperative cancellation behavior. Cancel remaining stays available in the processing queue.

Batch settings are stored in ai_settings and retained for retries. Existing rescan behavior deliberately takes the current admin default in a new immutable batch; the newly uploaded batch's choice does not mutate earlier scans. The batch summary shows Local LLM on/off, while each paper's Local AI details show its actual off/ran/timeout/error result. A configured AI-on batch does not prove successful inference on every paper.

## Ollama input scope

The existing AI input path was inspected, not replaced. One bounded request per paper includes all extracted readable source segments, all 39 official rule texts and existing candidate metadata. It does not send the raw PDF/DOCX binary, original formatting, or page images. Excluded noise is not used as source. If a paper exceeds the 512-segment cap or the conservative context/output budget, AI reports an explicit source/context-budget error and preserves the rules/semantic result, marking the paper incomplete. It does not silently trim to flagged excerpts or chunk an over-budget paper.

## API for the parallel UI work

POST /api/batches?ai_mode=off — explicit rules + semantic only.
POST /api/batches?ai_mode=on — explicit local LLM opt-in using the configured model and a verified per-batch digest.
POST /api/batches?ai_mode=default — legacy behavior using the current admin default (also used when ai_mode is omitted).

The multipart body still contains files only. The API rejects unknown mode values. AI-on readiness failures return HTTP 422 with an actionable message and create no batch. The response retains the existing BatchRecord contract and records the final ai_settings snapshot. GET /api/ai supplies local availability/configuration for the selector. Admin-only model/default settings and their authentication are unchanged.

Changed frontend files: UploadBatch.tsx, new BatchSelection.tsx, BatchSummary.tsx, AIControls.tsx, AISettingsForm.tsx, new logic/uploads.ts, workflow.css and api/client.ts. The latter also recognizes the existing document context-scope value. Changed backend files: api/batches.py and new core/batch_ai.py. Frontend test runner targets Node 20 for its async metadata contracts. Do not replace the parallel UI redesign wholesale; carry these behavior/API contracts into it.

## Validation

- Full backend suite: 636 passed, five optional live-Ollama checks skipped.
- Targeted batch/AI/workflow suite: 25 passed, including opt-in with admin default off, opt-out with default on, model/context rejection, persistence and retry behavior.
- Strict mypy: 113 files passed; Ruff passed.
- Production frontend build, ESLint and formatting checks passed. Frontend metadata/render contracts: 24 assertions passed, including the 100-file boundary and an empty directory following the 100th file.
- In-app browser: mixed PDF/DOCX staging, Add, Remove, Cancel selection, unavailable-AI blocking, keyboard focus and actual explicit-start upload verified. Both uploaded format fixtures completed with AI off and List 1 then List 2 traces.
- A loopback-only test proxy delayed one upload acknowledgment by four seconds. The browser displayed cancellation pending, then sent POST /cancel and received HTTP 204. Its tiny fixture had already completed and was retained as documented. The proxy and temporary browser tab were stopped/closed afterward.
- No browser console errors were observed in these checks. A separate headless Playwright harness could not launch in this execution environment; browser checks used the in-app browser instead. No new automated Axe or responsive audit is claimed for this change.
- All 92 original M12 evidence artifacts remain unchanged. Official rules, scoring and v6 detection logic were not edited. No new accuracy measurement was made, and the 80-paper AI-on accuracy remains unmeasured. AI-on protocol tests used a deterministic provider stub, not real Qwen inference.
- Initial source/build backups are in the prechange snapshot directory recorded in validation.json. The separate spr-ui-redesign directory was not modified. A fresh offline distribution ZIP was not built.
