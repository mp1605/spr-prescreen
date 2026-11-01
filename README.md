# SPR Pre-Screen · M13 development improvement

The active backend now uses `LOE2-guide-v5-admin` and semantic bands 0.84/0.86. On the
60 development papers, recall improved from 42/74 to 68/74 (91.9%), List 1 recall reached
23/23, and unmatched passages fell from 733 to 86. These are tuned development results;
new unseen-data performance has not been established. Frontend files were not changed.
See `reports/m13/M13_REPORT.md` and `docs/M13_BACKEND_UI_HANDOFF.md`.

New development results: `/api/evaluation/development/latest`. Original M12 scorecard
endpoints and archived evidence remain unchanged. Existing services need a deliberate
backend restart to load the changed code/configuration; the isolated 8520 service is updated.

## Original M12 frozen evaluation

The separately authorized evaluation has completed on 80 sponsor test papers, with one
holdout pass and no scanner tuning. **Accuracy targets were not met.** Holdout trigger
recall was 15/25 (60%); paper-color accuracy was 10/20 (50%). Across the full dataset,
all 20 green test papers received findings. Do not treat software test success as
screening reliability. The tool never determines release.

Measured Dev/Holdout reports are visible in `/scorecard` after restarting the backend.
`reports/TEST_REPORT.md` includes the measured results, every missed trigger and unmatched
passage. `reports/M12_EVALUATION_REPORT.md` explains the freeze, mappings, timings and limits.
No separate cleared-paper corpus was present in the supplied folder; its false-alarm
rate and AI-on accuracy/timing remain unmeasured. Scanner settings still exclude sponsor
examples and reviewer feedback from matching; the evaluation reader is separate.

The source, active policies, settings, official guide and model identity were frozen before
evaluation. The holdout ledger refuses another run, including after a failed attempt.
To inspect saved results without inference: `.venv/bin/python -m backend.eval status`.
The explicit authorized run command is `.venv/bin/python -m scripts.evaluate_m12
--authorized-sponsor-evaluation --papers <Tests> --keys <Keys> --crosswalk
reports/evaluation/rule-reference-crosswalk.json`. It refuses existing claimed output.

Earlier milestone descriptions below document their state at that stage; M12 supersedes
their statements that evaluation is deferred. M10 hardware checks and the unchanged
historical distribution ZIP remain subject to the limits in the M11/M12 reports.

## M11 workflow (historical milestone summary)

M11 adds cross-batch **Review by item**, original-layout source evidence, sequential
accept/override/undo, filename/color/review filters, pagination, and exact-finding links
to full paper review. **Evaluation scorecard** has working keyboard-accessible Dev/Holdout
tabs and status export. Sponsor measurements remain explicitly **Not measured** during
the blind build; no sample papers or keys were used to implement these screens.

Validation and precise remaining acceptance limits: `reports/M11_REPORT.md`.
Frontend source map and behavior: `docs/M11_UI.md`. Existing M10 bundle is a historical
artifact and does not contain this M11 frontend. Rebuild a distribution when required.

An offline, human-review application for APEX LOE 2. Native PDF/DOCX review copies
now default to red/yellow highlights only. Word review uses cached, paginated pages;
PDF review retains the original page orientation. Existing screening, batch review,
admin indicator management, versioned rescans and report exports remain functional.
M9 optional local Ollama integration has passed protocol tests and real local-model
validation with the bundled Qwen model. AI stays off by default. The tool never determines release.

Pre-screen only — a reviewer makes the release decision.

## Run the prepared project

From this directory:

```sh
./run.sh
```

Open `http://127.0.0.1:8501`. The launcher validates the official registry and source
PDF hashes, checks the built frontend, verifies all declared model hashes, and binds
Uvicorn exclusively to `127.0.0.1:8501`. Set `SPR_NO_BROWSER=1` to skip opening a browser.
The prepared environment uses Python 3.11.14.

The project is located at `/Users/mpatel/Projects/spr-prescreen`. A Python 3.11.14
runtime is included at `runtime/python3.11/`; the active `.venv` was rebuilt at this
location using only the vendored packages.

The working UI includes batch upload and a greens-first queue, evidence review, searchable
official rules and source PDF, system status, responsive navigation, and a persistent
light/dark theme. All assets are local.

## Browser screening and review (M4)

1. Choose files or a folder, or drop either onto the upload area. Up to 100 files, each
   at most 25 MiB. PDF/DOCX files are processed; excluded keys/metadata, unsupported
   formats, and oversized inputs are listed as rejected. No directory is discovered automatically.
2. Follow actual per-file parsing/List 1/List 2/AI-off status through SSE notifications
   and polling fallback. Cancel stops pending work and discards in-flight output;
   it does not kill an active parser process. Retry starts a new attempt on retained originals.
3. The queue starts with greens first. Sort by red or flag count; filter by color,
   list, item or review state, and search file titles. All uploads, including errors,
   remain visible. Select older batches from the batch menu.
4. Open a paper. Click a flag to navigate to its exact paragraph or PDF rectangle.
   Word files open as paginated previews from a project-owned LibreOffice runtime.
   Native highlights are rendered in place. Invisible source bookmarks drive page navigation;
   evidence without a visible page anchor remains in a labeled excerpt section.
   PDF pages retain their saved orientation; the overlay transforms source coordinates
   with the page. Accessible page text and original-file downloads are available.
5. Enter a reviewer display name. **A** accepts, **O** opens override with optional
   reason/presets, **J/K** selects next/previous flag, **N** opens the next paper in
   greens-first order, and **U** undoes your latest active decision. Shortcuts pause
   while typing or in the override dialog. Flag buttons also work with keyboard navigation.
6. Decisions update optimistically, then persist to an append-only audit trail. Undo
   appends a reversal; it can restore an earlier decision. Another window's revision
   conflict triggers a refresh rather than an overwrite. Findings, colors and source
   offsets stay unchanged. Duplicate uploads have independent reviews even for identical bytes.
7. Flagless papers require explicit **Mark source inspected** to count as reviewed.
   Incomplete sources also require that acknowledgment after reviewing any flags.
   Inspection does not resolve missing source content or make a release decision.

Browser runs live in `runs/web-<uuid>/`: atomic `results.json`, separate append-only
`decisions.jsonl`, and per-upload private original/parse files. Files use mode 600 and
new directories 700. Reloads and restarts preserve completed runs/reviews. Interrupted
jobs become visible failures, with retry available. Do not run two backend processes
against one run directory: prototype revision locking is within one service process.
Reviewer display names are an audit label, not authenticated identities; admin access
control is implemented in M8 for indicator management. Annotated downloads and CSV/JSON exports are available below.

## Semantic screening (M5)

The default app and screening CLI now run **E1 + E2 on List 1, then E1 + E2 on List 2**.
The local CPU model is `BAAI/bge-small-en-v1.5` through fastembed, producing 384-dimensional
vectors. All 39 item texts are embedded as official references. There is no sponsor-key
exemplar bank, corpus discovery, external API inference, or synthetic trigger bank.

Every extracted source segment is embedded once per paper, in batches. Tokenizer-aware
windows cover passages longer than the 512-token model input, with overlapping windows
and a checked payload limit; text beyond the first window is not silently discarded.
Similarity is the maximum cosine across a segment's windows against each official item.
Candidates at `mid_threshold` (0.65) or above are retained; the `high_threshold` (0.80)
labels high similarity. These are **retrieval bands, not calibrated probabilities**.
Thresholds were not adjusted using papers, keys, expected results, or these format fixtures.
Even generic headings can produce candidates; applicability remains a human judgment.

List 1 candidates follow the specification's existing red severity. Semantic-only List 2 candidates remain yellow, including high-similarity matches.
M6 can promote E1-anchored matches with the source facts described below.
The interface names the engine, displays actual cosine values and up to three nearest
matching **official references**, and explains uncertainty. `nearest_exemplar` remains
null because no permitted keyed-trigger exemplars were supplied for this blind build.

A paper has one semantic session. Model/reference state is shared behind a bounded
inference lock; paper sessions cannot exchange source vectors. A private, bounded,
pickle-free vector cache is keyed by model identity, source SHA and segmentation/text
fingerprint. Model assets are hash-verified and loaded from an explicit local directory.
Cache hashes, shape, dimensions, finite values and norms are validated. Corrupt caches
are recomputed; cache-write failure retains a valid fresh inference. Model/window/vector
failure preserves E1 findings, still attempts both lists, and marks screening Incomplete.

Each result records model/reference fingerprints, bands, reference source, calibration
state, completion state, segment/window counts, cache state, and semantic timing.
Semantic findings name only existing official IDs and retain exact source evidence.
Old runs retain their original stage and colors; their raw records are not rewritten or silently rescanned.

Reviewer accept/override stores a positive/negative feedback reference in the same atomic
append-only audit event. The feedback view resolves its quote from the immutable finding;
document quotations are not duplicated into the audit log. Undo withdraws that active
example or restores its predecessor.
The active examples are available in the decisions response and audit view, but remain
**excluded from matching while this blind build is active**. No past run is harvested
into the semantic engine. This preserves the user's restriction while making feedback
capture, polarity, provenance, persistence and undo functional.

For a reproducible throughput check using only official-text format fixtures:

```sh
.venv/bin/python -m scripts.benchmark_m5
```

It processes 40 DOCX containers holding the official item wording and 40 copies of the
official PDF with varied container metadata. It reports parsing, E1-only, E1+E2 cold,
and warm-cache timings, with startup separate. This is not an 80-paper sponsor evaluation,
a recall measurement, or a representative estimate for 80 unrelated papers. See
`reports/M5-benchmark.json`, `reports/M5_REPORT.md`, and `reports/M5-pytest.txt`.

## Source fusion and specificity (M6)

Overlapping passages merge within one list and one source unit. A multi-item passage
counts as one flag; different lists, disjoint passages, pages and Word parts remain
separate. PDF rectangles are recomputed from source words. All item IDs, engine names
and the three strongest official references are retained.

List 1 stays red. For List 2, a rules-anchored topic plus an item-specific combination
of literal quantities, named units/places, dates, system/program designators or other
source facts can be red. Each item has its own assessment; the strongest item determines
the passage color, while possible items keep their uncertainty explanation. Paper color
is the worst flag color. Semantic-only, conditional, illustrative, negated-disclosure,
or insufficiently specific matches remain yellow. National-interest, policy-impact,
controversy and external DOPSR-designation items require judgment and stay yellow.
OPSEC, TTP and critical-technology items have stricter evidence requirements.

Facts must occur in the topic's same source sentence, within 180 characters of the
matched topic. Exact quoted feature spans and topic anchors are validated against the
immutable source. URI/DOI fragments and ambiguous year-like quantities are guarded.
Future dates use the recorded UTC assessment date, not a hard-coded year. Optional
hash-verified local spaCy NER supplies places; arbitrary organization names do not prove
DoD coordination. Regex features work when NER is unavailable; its state is recorded.

The review card exposes each item's color reason, matched words and source facts.
Results record fusion/specificity versions, a code/policy fingerprint, assessment date
and optional NER model identity. These enter deterministic finding IDs. A classification
failure preserves candidates as yellow (List 1 stays red) and marks the paper Incomplete.
A 50,000-character passage / 512 regex-feature budget prevents unbounded classification.

These are conservative engineering heuristics, not a classification determination.
Being in the same sentence does not prove that every fact relates to the topic; complex
clauses can still cause false promotions. Paraphrases and unrecognized entities can stay
yellow or be missed by retrieval. No scanner accuracy has been measured on sponsor papers.
The named-paper and development color-accuracy acceptance checks remain deferred under
the user's blind-build restriction. Annotated exports are available in M7 below.

## Annotated copies and reports (M7)

In Paper Review, **Annotated DOCX/PDF** downloads a copy with native red/yellow highlights
and notes containing official item IDs, source evidence, reasons, uncertainty and the
current reviewer decision. Original content and scanner findings are never edited.
Overridden flags retain their raw screening color; notes identify the override and reason.
A summary comment/note records the original SHA-256, rules version, AI state, review
revision, incomplete status, and the human-decision disclaimer. Flagless copies also
receive that summary. The **Copy details JSON** button downloads both original and copy
SHA-256 hashes, review revision, annotated flag count and any annotation limitations.

DOCX exports preserve run formatting and hyperlinks while splitting text at exact evidence
boundaries. Cross-list overlaps display the worst color and retain every finding's note.
Existing comments and untouched package parts remain intact. Word inline comment anchors
are placed in the main body, including tables. Headers/footers, footnotes/endnotes,
existing comments and text boxes are highlighted in place, with their finding notes on
the document summary; the UI and manifest explicitly identify this placement. A complex
run that cannot be mapped exactly produces a visible failure rather than a guessed range.
Existing highlights outside evidence remain unchanged. In PDF, the original text, page
geometry/rotation and existing annotations remain intact; each finding gets a native
highlight with its item note. Annotations are not burned into the page image.

In the queue, **Export CSV / Export JSON** includes the **entire selected batch**, even
when filters hide entries. A locked snapshot combines results with review states. JSON
contains full findings, specificity/semantic provenance, active decisions and the complete
audit trail, including undo. CSV has one row per finding, plus explicit rows for flagless,
failed, rejected, cancelled or pending entries. It includes source inspection history,
per-flag decision history and current decisions. CSV is UTF-8 with BOM; potentially
executable spreadsheet cells are prefixed with an apostrophe. JSON retains exact text.
Unscreened entries have no invented result/color or AI execution state.

Every report distinguishes stored original SHA-256 from the currently retained source
hash, with `verified`, `mismatch`, `unavailable`, `not_screened` or `not_retained` status.
Missing/changed originals do not prevent report export. Annotated copies require the
original hash and source evidence to match. Signed files, unreadable originals, unusable
PDF coordinates, or unsupported Word ranges produce explicit errors; export the report
and inspect the original manually. Signed sources are never silently altered.

Derived files live under `runs/<run_id>/annotated/`, keyed by entry, result, review and
annotation-code identity, alongside manifest JSON. Repeat downloads reuse a hash-checked
copy; review changes create a new artifact. Batch `report.csv` / `report.json` are replaced
atomically on request and contain their own snapshot timestamp/revisions. Files are mode
600, new directories 700. Existing run results, decisions and originals remain unchanged.

Local endpoints:

- `GET /api/batches/{run_id}/export/csv` or `/export/json`
- `GET /api/batches/{run_id}/papers/{entry_id}/annotated`
- `GET /api/batches/{run_id}/papers/{entry_id}/annotation-manifest`

This is export functionality, not a release determination. The named sponsor/key visual
acceptance check remains deferred; annotation correctness was tested using official
wording and format/coordinate contracts. See `reports/M7_REPORT.md` and `M7-pytest.txt`.
Authenticated rule management is available in M8 below.

## Local admin and rule management (M8)

Initialize the main project admin **in your own terminal**, from this directory:

```sh
.venv/bin/python -m backend.admin init
```

The CLI prompts privately for a 12–1024-character password and confirmation. It stores
an Argon2id hash, generation and setup timestamp in `config/admin.json` with mode 600.
There is no default password, browser registration or password command-line argument.
The delivered main project has no test admin account. To deliberately replace the
password and invalidate existing sessions:

```sh
.venv/bin/python -m backend.admin reset
```

On **Official rules**, use **Manage indicators** to reach the admin section. Reviewers
retain read-only policy access. Sign in with the local admin password. The HttpOnly,
SameSite=Strict cookie is scoped to `/api/admin`, with a 30-minute absolute expiry.
Sessions live only in service memory and are invalid after logout, reset or restart.
There are at most five sign-in attempts per minute for this loopback service. Cross-origin
writes are refused. This is a shared-password local prototype, not production identity.

1. **New indicator draft** copies the active policy into a private saved draft. Existing
   drafts can be selected and resumed. Edit the YAML, then **Save draft**. The editor
   reports unsaved changes; reloading a saved draft replaces them.
2. **Validate saved draft** checks schema, IDs, regex compilation, detector references,
   unique names and configured E1 coverage. It shows each changed field side by side.
   Official wording, categories/examples, source, item numbering, execution order and
   color rules are protected; edit detectors only. YAML aliases, excessive nesting,
   oversized drafts and detector budgets are refused. Version numbers are assigned on
   publication rather than typed into the draft.
3. **Start impact preview** processes only explicitly selected PDF/DOCX files (1–100,
   at most 25 MiB each), with the current and candidate E1/E2/specificity snapshots.
   Source hashes, before/after flags, evidence, item changes and color changes are shown.
   Parsing is process-isolated and the single preview worker reports real progress.
   No folders, previous runs or sponsor directories are searched. During the blind
   build, select only permitted non-sponsor inputs. Accuracy and recall are not measured.
4. Enter a change note and **Publish rules** after an eligible complete preview. Any
   draft edit invalidates validation/preview; another publication makes old-base drafts
   stale. Concurrent-window revisions are checked. Incomplete or failed previews cannot
   authorize publication. Publication uses immutable `policies/versions/rules_vN.yaml`,
   updates the active manifest/mirror, and appends the admin, note, hashes and preview ID
   to the policy audit. New batches use the new version immediately.
5. **Restore as draft** takes a checksum-verified earlier runtime version through the
   same validation and preview gates. **Publish rollback as new version** restores its
   contents under a new monotonic version, with a rollback audit event. The original v1
   scaffold lacks complete detectors and is shown as history rather than a runnable
   rollback target. Existing complete runtime versions and new published versions work.

Drafts and explicit preview inputs/results persist privately under `policies/drafts/`
and `policies/previews/` (gitignored). They contain policy edits and potentially source
text; they are not harvested into semantic retrieval or evaluation. A restart invalidates
an unfinished preview and requires a fresh scan. Saved drafts remain available after login.
No sponsor labels, keys, exemplar banks or recall scorecards feed this workflow.

Publication uses a POSIX file lock and a prepared journal. On restart the journal can
complete a partially written authorized publication and append its audit event exactly
once. Unexpected external changes fail recovery instead of being silently accepted.
Startup still rejects a manually edited active YAML or altered official PDF with a clear
integrity error. If a publication reports incomplete storage, restart the service to
recover it; preserve the journal if integrity recovery fails. Run one backend per project.

Each queued/running batch holds its original engine snapshot. Publication does not change
mid-batch policy, old results, audit decisions or annotated-copy provenance. In the queue,
**Rescan with current rules** creates a separate batch from that explicitly selected batch's
retained originals. Previous reviews remain with the original batch. Missing, rejected or
hash-changed originals become visible rejected entries instead of silently substituted input.
No new upload or source corpus is discovered automatically.

M8 was tested using official-wording and mechanical format contracts, including a numerical
provider that isolates rule changes from semantic retrieval. The full browser flow also ran
with actual BGE on one official-heading format file. These checks are not scanner accuracy.
See `reports/M8_REPORT.md` and `M8-pytest.txt`. Next milestone: M9, optional local AI.

## Authority and blind-build constraints

`MASTER_PROMPT.md` is the sole engineering specification. The user's instructions in
`docs/AUTHORITY.md` take precedence where they restrict evaluation access. No earlier
AEGIS prompts or amendments are used.

`docs/official-lists.pdf` is the supplied four-page policy source: List 1 appears on
pages 1–2 and List 2 on pages 3–4. The source was visually verified and all 39 item texts
are tested against direct extraction. List 1 has IDs L1-1, L1-3 through L1-9; List 2
has IDs L2-01 through L2-31. No item 2 was invented. Whitespace and invisible PDF
characters are normalized; wording, spelling, and numbering are preserved.

The registry preserves official wording and examples and now contains independently
implemented, official-ID-bound E1 detector definitions. No sponsor papers, keys, indexes, expected
results, or key-derived detector hints or exemplars are imported. `data/` stays empty
and gitignored. No sponsor accuracy measurements have been made.

## Evaluation harness (M3 — sponsor evaluation deferred)

```sh
.venv/bin/python -m backend.eval self-check --output reports/M3-self-check.json
.venv/bin/python -m backend.eval status --report reports/TEST_REPORT.md
.venv/bin/python -m backend.eval run --split dev
```

The first command exercises six in-memory official-text format/math contracts. It parses
DOCX/PDF formatting and checks scoring arithmetic; **it does not run the scanner or measure
scanner accuracy**. The status command reports the actual blind-build state. The run command
intentionally returns exit 2 before discovering or reading any sponsor dataset, scanning
papers, or claiming the holdout. There is no development unlock flag.

This follows the user's instruction to conduct sponsor evaluation separately after
implementation. No `eval/gold.jsonl` or development scorecard is generated from sponsor
material during this build. The specified 99-trigger/corpus checks remain unverified.

The harness functions are implemented under `backend/eval/`:

- `parse_key_bytes` reads explicit caller-provided DOCX/PDF bytes. It extracts bold trigger
  passages, superscript Word tags, answer rows, expected color, and quoted decoy lines.
  Duplicate/missing tags, unknown IDs, ambiguous references/colors, and inconsistent color
  labels fail rather than becoming guessed gold data. No key-file paths are opened by it.
- Gold JSONL serialization round-trips validated cases with atomic private writes. This
  capability is not called on sponsor data while the runner is locked.
- The frozen split contains the specified 60 development and 20 holdout IDs only. This is
  metadata, not sponsor content or labels. A one-shot atomic holdout ledger refuses a second
  claim even after failure or a changed fingerprint; only temporary contract ledgers were
  used in tests, not the project's real holdout state.
- Passage matching uses a maximum-cardinality one-to-one assignment. A broad finding cannot
  claim several triggers. Item agreement is mandatory. Text agreement is at least 50%
  multiset coverage of gold tokens OR normalized partial ratio at least 80%. Identical
  cross-list evidence is grouped; duplicate same-list findings remain extra candidates.
- Metrics include headline and per-list trigger recall, matched-item micro Jaccard, matched
  flag-color accuracy, paper-color accuracy, a 3×3 confusion matrix, misses, false alarms,
  decoy hits, green-reference findings, reference-paper false alarms, incomplete counts,
  AI-off/on timing, and the stated engineering cost `3 × misses + false alarms`.
- Missing/extra cases, duplicate IDs, source-hash disagreement, and empty datasets are
  refused. Zero denominators yield `null` / “Not defined”, not perfect scores. List-specific
  recall requires agreement on an ID from that list.
- Markdown reporting includes full missed-trigger and decoy quotations, unmatched findings,
  a plain “Where it fails” account, timing scope, and limitations. Untrusted quotes are
  fenced as text. Contract reports are prominently marked **NOT SCANNER ACCURACY**.

Readers are strict about the described format: Word body/table paragraphs, bold passages
adjacent to tags, page-contained PDF passages and extractable ruled tables. Unreadable,
encrypted/repaired, revised, or ambiguous layouts require manual correction. The functions
have been verified with official-wording format contracts; compatibility with sponsor keys
has deliberately not been tested. Neither keys nor expected labels feed the scanner or its
exemplar source. The scanner has no import dependency on the evaluation package.

## Pre-screen documents (M6; explicit M2 baseline available)

From the project directory, name explicit PDF/DOCX inputs:

```sh
.venv/bin/python -m backend.screen docs/official-lists.pdf --output runs/guide-screen.json
.venv/bin/python -m backend.screen /path/to/document.pdf /path/to/document.docx --workers 2 --output runs/batch-screen.json
```

This runs E1 and E2 against **List 1 first, then List 2**, unconditionally. List 1
candidates are red; List 2 candidates receive the M6 per-item specificity checks. Green means only that neither
engine found a candidate in the readable source. Each result identifies
`screening_stage=rules_semantic`, its semantic provenance, rules version, ordered trace,
quotations/locations, flag counts, and `NOT_MADE_BY_TOOL` release decision.
For an explicit E1-only diagnostic baseline, add `--rules-only`; this is labeled
`screening_stage=rules_only`; it retains preliminary colors and does not run M6 fusion.

67 data-defined indicators cover all 8 + 31 official IDs: portion/control markings with
letter-list guards, personal-information formats, acknowledgment medical context,
per-item keyword/regex lexicons, and a guarded O-7-or-higher author-byline check. Matching
normalizes Unicode/whitespace with a source offset map; evidence remains unchanged source
text. Formal references or public contact information can cause false alarms, and
paraphrased or contextual concerns can be missed. Applicability requires human review.

Multiple indicators/items in one source segment and list become one passage flag. List 1
and List 2 remain separate findings. Finding IDs are deterministic for the same paper,
policy version, semantic configuration/model, fusion/specificity code, optional NER
model, assessment date, list and source span. No probabilities
or exemplar scores are invented. Raw parsed sources and findings are immutable.

An engine failure records `list1:error` or `list2:error`, preserves valid findings, runs
the other list, and makes the result incomplete rather than green. Corrupt/unreadable
inputs remain yellow/incomplete unless an existing red finding wins. Rejected inputs and
unreadable paths remain separate, explicit records in the batch report.

The CLI writes a private, atomic JSON report and prints counts only. Exit 0 means
processing completed; red/yellow flags are not command failures. Exit 2 means a processing
problem, rejected input, unreadable input, or invalid arguments. `seconds` in each paper
measures E1/E2 and fusion/specificity, including first-use lazy model setup. The top-level timing
measures parsing and combined parsing/screening wall time, excluding input reading
and report writing. In `--rules-only` mode, per-paper time measures only E1.
Without `--output`, a unique `runs/screen-.../results.json` is created. `--no-cache` disables
parse and semantic-vector caching; it does not change screening logic.

Detector definitions are part of the integrity-checked `policies/official_rules.yaml`.
The current engineering baseline is `LOE2-guide-v3-E1`; earlier snapshots and bootstrap
audit entries are preserved under `policies/versions/` and `policies/audit.log`. Official
wording, examples, numbering, source pages, and source-PDF hash are unchanged. The authenticated admin workflow below publishes indicator changes; the engineering bootstrap versions remain preserved.

The Rules page exposes the active indicator names and version read-only. The health API
reports the current rules+semantic stage. HTTP batches and browser evidence review
are functional. Local generative AI remains off; sponsor accuracy is not measured.

## Parse documents (M1; parser revised in M2)

From the project directory, explicitly name the PDF/DOCX inputs:

```sh
.venv/bin/python -m backend.ingest docs/official-lists.pdf --output runs/guide-parse.json
.venv/bin/python -m backend.ingest /path/to/document.pdf /path/to/document.docx --workers 2 --output runs/batch-parse.json
```

The command writes extracted text and evidence locations to the chosen JSON report.
Without `--output`, it creates a uniquely named run under `runs/`. It prints counts only,
not document text. Exit 0 means every input parsed completely; exit 2 means an input was
incomplete, rejected, unreadable, or an argument failed validation. An unreadable path has
an explicit `input_errors` record and no fabricated content hash.

Each readable input receives `sha256:<full-file digest>`. The same bytes under a different
filename reuse the parse cache; different bytes under one filename receive different IDs.
Parser version 2 corrects PDF style-block splits before lowercase sentence continuations;
v1 cache entries are not reused. Cache files are versioned, limits-sensitive, checksum-checked,
atomically written with mode
600 under `runs/cache/parse/`, and can be disabled with `--no-cache`. Cache failure preserves
the fresh parse and is reported as `cache_state=unavailable`.

All parses record `screening_state=NOT_SCREENED` and
`release_decision=NOT_MADE_BY_TOOL`. Complete parsing has **no green screening color**.
Incomplete/rejected content has `review_color=yellow`; it must never be treated as a clean
screening result. Corrupt, encrypted, image-only, or partly unreadable files do not prevent
other files in a batch from parsing.

Limits: 25 MiB/file, 100 files/batch, 1–4 worker processes; defaults use 2. Defensive parser
budgets cover 1,000 PDF pages, 25,000 Word paragraphs, 2 million extracted characters, 5,000
DOCX package entries, and 100 MiB expanded DOCX content. Reaching a limit is explicit and
incomplete. Oversized CLI inputs are hashed in a stream without retaining the whole file.

Source text is not rewritten when boilerplate is excluded. Each source unit retains
`text`, `excluded` spans, and its page or global paragraph number. Segment quotations are
exact slices at `char_start:char_end`. PDF rectangles use **unrotated PDF points** and
require the same page rotation transform as the document image when displayed later.
Word units include their OOXML `part`, global paragraph index, heading context, run spans,
and direct run formatting. Body paragraphs, table cells, headers/footers, footnotes,
endnotes, comments, and text-box paragraphs are retained without following hyperlinks.

Only the documented banner line, `(fictional author)` tag, `Fictional source:` line, and
standalone `Page N`/`Page N of M` forms are excluded. Unknown or differently wrapped
boilerplate remains available for review. Layout order is best-effort; unusual columns
and PDF glyph encodings need human inspection. OCR is not performed. PDF raster images,
Word visual/embedded content, and tracked revisions produce explicit review issues rather
than an assumption that all content was read. Tracked text is retained where extractable.

The ingestion module receives bytes and never discovers evaluation files. The CLI accepts
explicit paths only; obvious key, holdout, index, and expected-result paths are blocked.
During development, do not pass sponsor samples or tests to it. Such a name guard is not a
content-based key detector and does not replace the blind-build operating constraint.

## Offline installation on the same platform

This prepared wheel set targets **macOS Apple Silicon, Python 3.11**. Other operating
systems and architectures need their own wheel downloads before disconnecting.
The bundled `runtime/python3.11/bin/python3.11` can create the environment on compatible
macOS Apple Silicon machines. Alternatively, use another compatible Python 3.11 installation.

```sh
runtime/python3.11/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links vendor --require-hashes -r requirements.txt
.venv/bin/python -m pip install --no-index --find-links vendor --require-hashes -r model-requirements.txt
./run.sh
```

Keep `models/`, `vendor/`, `runtime/`, and `backend/static/` when copying the project. The frontend
is already built; Node and npm are not needed to run it. The prepared `.venv` is local
and should be recreated after moving the project. Model assets include the BGE small
384-dimensional ONNX embedding model and spaCy `en_core_web_sm` 3.8.0. Ollama is optional,
disabled, and not downloaded or launched in M0.

The launcher sets `HF_HUB_OFFLINE=1` and `ORT_DISABLE_TELEMETRY=1` before model loading,
disables Hugging Face telemetry, and uses project-local caches. The ONNX process-start
switch is required in addition to its Python disable call; see the
[official runtime guidance](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md).
Direct app/CLI/model entry points apply the same bootstrap and reject late configuration. The cached model inference test forbids Python socket and DNS access.
**The outbound socket airlock and complete offline bundle checks belong to M10.**
M5 does not claim full network isolation.

## Online setup / development

Use Python 3.11 and Node 20.19 or newer. Network access is needed only for setup:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
./scripts/vendor.sh
.venv/bin/python -m pip download --no-deps -d vendor https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
.venv/bin/python -m pip install --no-index --find-links vendor --require-hashes -r model-requirements.txt
.venv/bin/python scripts/prepare_models.py
cd frontend
npm ci
npm run build
cd ..
./run.sh
```

`requirements.in` declares direct dependencies. `requirements.txt` locks all transitive
Python dependencies with hashes. `frontend/package-lock.json` locks the frontend tree.
Model-file hashes live in `models/manifest.json`.

Vite writes the static build to `backend/static/`, following its
[documented output-directory configuration](https://vite.dev/config/build-options).
FastEmbed's [official model reference](https://qdrant.github.io/fastembed/examples/Supported_Models/)
documents the required BGE small model and 384 dimensions.

## Checks

Build the frontend before running integration tests:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend tests scripts
.venv/bin/ruff format --check backend tests scripts
.venv/bin/mypy
cd frontend
npm run lint
npm run format:check
npm run build
```

Tests use the supplied guide, format fixtures transcribing its official wording, and contract
objects, not sponsor papers or synthetic paper datasets.
They cover evidence requirements, valid IDs, execution-order contracts, uncertainty,
color/count consistency, immutable findings, UTC decisions, policy integrity, malformed
YAML startup failures, duplicate YAML keys, detector references/regexes, loopback settings,
HTTP routes, source fidelity, and cached model inference. This tests the foundation;
it does not establish scanner behavior or accuracy. M1 adds parsing, geometry, noise-removal, cache, resource-limit, process-pool, and CLI tests.
M2 adds official-wording indicator coverage, marking/PII/byline guards, actual list order and
error traces, grouping, immutable evidence, screening CLI, and disabled-network/key-access checks.

## API available now

- `GET /api/health`: milestone, screening availability, actual policy counts/version.
- `GET /api/rules`: the validated read-only official registry.
- `GET /api/rules/source`: original official PDF.
- `GET /api/system`: local runtime configuration and model readiness.

- `GET/POST /api/batches`: list durable runs with review progress / upload multipart files.
- `GET /api/batches/{run}` and `GET .../{run}/events`: results / resumable SSE notifications.
- `POST .../{run}/cancel`, `POST .../{run}/papers/{entry}/retry`: cancel remaining / retry.
- `GET .../{run}/papers/{entry}` and `/document`: raw result / extracted source.
- `GET .../{run}/papers/{entry}/pages/{number}.png` and `/original`: page render / original download.
- `GET/POST .../{run}/papers/{entry}/decisions`: audit state / accept, override, inspect, undo.

Unknown API paths and private filesystem paths return 404. Cross-site browser writes
are refused. Policy editing remains unavailable until M8. The policy hash detects edits
relative to `active.json`; it is not a signature or a defense against replacing both.

## Milestones and limitations

M0 through M5 are implemented. M6 is next: span fusion, specificity and final List 2
color handling. M5's official-text checks and 80-container timing exercise do not measure
sponsor recall or false alarms. All sponsor-based calibration/acceptance and keyed-trigger
exemplars remain deferred to separate blind evaluation after implementation is complete.

Admin initialization is not implemented yet. Evaluation self-check/status commands work;
sponsor execution remains intentionally locked during development. There is no
default admin password, simulated scan result, or inactive feature button.

## Layout-preserving review copies

**Highlighted DOCX/PDF** adds native red/yellow highlights while keeping the source
format. **Include review notes** is off by default; turn it on for item IDs, provenance
and reviewer-decision comments. Existing source annotations/comments are retained.
Copy-details JSON supplies source/copy hashes and the selected notes mode in either case.

Word page previews are generated only when opened, under one renderer lock, then cached
by source/result/code identity. Scanning does not wait for preview conversion. The bundled
macOS renderer lives in `runtime/LibreOfficeDev.app/` with its license/notice files;
Microsoft Word and a network download are not required. Macros are disabled in a fresh
profile. Externally linked resources and active linked fields are refused for page
preview; native highlighted downloads and source access remain available.

Word preview rendering can differ from Microsoft Word for unavailable fonts or unsupported
features. The downloaded DOCX retains its original OOXML layout and styling. Page previews
are bounded to 60 seconds, 100 MiB and 1,000 pages. Render failures show a working retry
and original download; they do not replace the document with reflowed paragraphs.

On a two-page mechanical fixture containing official phrases, scan completion was 3.3 s,
first Word preview 5.3 s, and a cached layout request 0.006 s. These measurements are
format/workflow checks, not sponsor accuracy or throughput benchmarks.

If an older backend process is still running, stop it in its terminal and launch
`./run.sh` again from this project to load the updated Python routes. Refresh the browser.
Existing completed results are not automatically rescanned or rewritten.

## Optional local AI implementation (M9)

AI settings are under System and require the existing local admin session to change.
Only cached local GGUF models reported by Ollama at `127.0.0.1:11434` are eligible;
the application does not pull models or use remote/cloud model metadata. Model/context
metadata and its reported digest are pinned when enabling AI. The reported digest is
not independent attestation of weights loaded by the external Ollama process.

AI receives the official items and source segments as untrusted JSON data. Its constrained
proposals must name valid items and be proved against source quotes before joining the
baseline. E1/E2 findings remain; AI cannot erase or downgrade them. Applicability and
specificity remain source-bound. Timeouts, malformed output, context overflow or service
failure retain baseline findings and mark screening incomplete. No automatic retry or
continuation silently omits the rest of a paper. Uploads pin AI settings for retries;
explicit rescans capture current settings. AI off preserves the existing screening path.

The integration has schema, quote-proof, timeout, merge, settings, snapshot and export
contract tests. Five opt-in checks have also passed against actual qwen2.5:3b inference:
AI off preserves E1/E2, source-verified AI tagging, addition to an isolated empty-candidate
contract, the literal injection instruction, and a real cold-model timeout. These checks
measure integration behavior, not sponsor recall or model interpretation accuracy. No
sponsor examples, keys, expected outcomes or prior user runs were used.

### Prepared local Ollama runtime

The verified macOS runtime is `runtime/ollama/` (Ollama 0.40.13). The qwen2.5:3b Q4_K_M
weights and manifest are in `models/ollama/`; all model layer hashes were verified.
Source checksums, the installer archive, file inventory and original licenses are in
`vendor/ollama/`. The official runtime keeps its small identity directory at `~/.ollama`;
the executable and model weights stay in this project. No login or cloud inference is used.

In a separate terminal, from the project directory:

```sh
./scripts/run_ollama.sh --verify
./scripts/run_ollama.sh
```

The helper verifies local files, binds only `127.0.0.1:11434`, disables cloud features and
request-body debug logging, and never downloads models or changes scanner settings.
Use `./scripts/run_ollama.sh --cpu` if Metal cannot create a GPU context. Do not start a
second server when port 11434 is already in use. Stop the owned terminal server with Ctrl-C.
Enable AI for new batches through the existing admin controls on System; the default
remains off. Main-project admin credentials and AI settings were not changed during QA.

Real validation here used CPU because this execution environment could not create Metal
command queues. The cold probe took 23.2 s; the formal source-binding case took 36.9 s,
with later checked calls at 6.0–7.4 s. Full UI stages took 67.6 s for Word and 44.8 s for
a standalone PDF; the paired PDF reached its 120-second queue/generation deadline and
retained baseline evidence. The 20-second default may time out on CPU or a cold
model. Set a larger per-paper budget in the admin form when using CPU; validation used
120 s, 16,384 context tokens and 512 maximum output tokens. The timeout includes waiting
for the single AI worker. Larger inputs can still exceed a configured context or deadline;
they are reported incomplete while retaining E1/E2 evidence. GPU performance is unvalidated.

Run the optional real-model checks explicitly, with the local server already running:

```sh
SPR_TEST_REAL_AI=1 .venv/bin/python -m pytest tests/ai/test_live_ollama.py -q
```

Ordinary test runs skip these five checks and do not require a model server. M9 is complete. M10 adds the Python network guard, observable offline status, managed
startup and portable installation. Physical Wi-Fi-off and second-machine acceptance
remain separate, unverified checks; see docs/OFFLINE_VERIFICATION.md.

## M10 offline operation and portable installation

At startup the Python backend permits only loopback sockets and local IPC. Outbound
hostnames are refused before DNS, IP connections/UDP are blocked, and wildcard listener
bindings are refused. Backend and spawned parser workers share a blocked-call counter.
The explicit screening/ingestion CLIs use the same guard. Offline status shows actual
listener observations, local model presence and loopback Ollama reachability, with clear
fallbacks when OS inspection is unavailable. Counters include intentional guard tests.

This is a Python network guard, not an operating-system firewall for every native process.
Native Word/Ollama use local-only settings; the full native workflow still requires the
physical disconnection checks described in `docs/OFFLINE_VERIFICATION.md`.

`./run.sh` validates official policy/model assets before serving, binds only loopback,
and starts cached project-local Ollama only when AI is enabled and no eligible service
is already running. The launcher does not download anything. It stops only processes it
started; an existing eligible Ollama service remains running. A busy backend port is an
explicit startup error. Use `SPR_NO_BROWSER=1 ./run.sh --port 8510` for an isolated port.

Build the prepared macOS arm64 bundle with:

```sh
./scripts/make_bundle.sh
```

The ZIP includes source, built web assets, Python/native runtimes, wheels and model files.
It excludes runs, source papers, evaluation data, reviewer decisions, credentials, sessions,
drafts and prior policy audit history. The current verified rule content becomes a fresh
bundle baseline; AI is off. No previous user records are read by the bundler. A per-file
manifest and ZIP SHA-256 accompany it. Frontend source is included for maintenance; npm
and node_modules are unnecessary to run the prepared application.

Extract with macOS Archive Utility or `ditto -x -k` to preserve permissions/symbolic links.
In the fresh `spr-prescreen/` directory run `./install.sh`. Installation checks macOS 14+
and arm64, verifies files, creates a new environment from the included Python 3.11, and
installs only hash-locked local wheels (`--no-index`). Existing environments are not
replaced. Initialize a new admin through the normal CLI if required.

After installation, `.venv/bin/python scripts/offline_smoke.py` checks a temporary
PDF/DOCX workflow with official phrases and zero expected outbound attempts. It does
not inspect existing runs or sponsor material. A copied-folder restore on the same Mac
is portability evidence; physical Wi-Fi-off and another-Mac verification remain separate.
