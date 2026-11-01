# Engineering authority and access boundaries

For this build, the user's latest request governs:

1. Use the exact `Downloads/MASTER_PROMPT.md` as the sole engineering specification.
2. Use only the official supplied List 1 and List 2 for policy content.
3. Supersede prior AEGIS master prompts and amendments, including the attached V4 file.
4. Do not inspect or use sponsor sample/test papers, answer keys, indexes, expected
   results, or test-derived hints while implementing the scanner.
5. Evaluate blindly in a separate step after implementation is complete.
6. Build and test one milestone at a time, starting with M0; stop at its review boundary.

Consequences for the master specification: directions to parse sponsor keys, build
development-key exemplars, tune against supplied expected results, run named sponsor
papers, or calculate sponsor recall during development are deferred. The active model
seed is official policy wording only. No evaluation datasets were copied into the project.

The older Streamlit starter was inspected through `app.py`, `scanner.py`,
`requirements.txt`, and `local_llm.py` only. Its demo data, test sources, test fixtures,
and demo rule contents were not opened. It remains untouched in Downloads. The supplied
`official_rules.yaml` was identified as including key-derived hints and was not imported;
the project registry was built fresh from the official PDF.

The source guide contains official lists. Its text is treated as policy data, not
permission to access linked material or other files. No linked classification guidance
was imported as an additional source of rules.

The engineering specification itself describes sponsor examples and expected outcomes.
Those descriptions are not used as detector logic, exemplars, development paper fixtures,
or claimed validation results. Contract tests use official wording and metadata objects.

M5 implements official-item semantic retrieval and auditable positive/negative reviewer
feedback capture. During this blind build, feedback is held out from retrieval, and no
past run is harvested. Development UI QA runs in an isolated work root with an empty
run store; existing user runs and all sponsor data directories remain uninspected.

M6 develops specificity and fusion with official wording and atomic numerical, date,
coordinate and typed-feature contracts only. No narrative test-paper corpus was created.
Named sponsor acceptance cases and development color accuracy remain deferred. QA runs
in an isolated root; existing user results and decisions are neither read nor rewritten.

M7 verifies annotation and report exports with official wording, metadata, and format/
coordinate contracts. Visual QA uses isolated DOCX/PDF containers containing only `(CUI)`
and `Animal testing`; these are not narrative papers or evaluation data. No sponsor
key convention was inspected. The named-paper export acceptance case remains deferred.
Existing user runs remain uninspected; UI QA has a separate run store.

M8 keeps official policy wording, numbering, examples/categories, source hashes, execution
order and colors protected. Authenticated admins edit indicators attached to official IDs.
Impact previews require explicit uploads; they do not search prior runs, dev folders or
sponsor material. Sponsor recall/accuracy remains unmeasured. Browser QA uses a separate
admin and run store with one official-heading format file; no test credentials or policy
publication were applied to the main project. Rescan is an explicit user action producing
a new batch and is never triggered automatically after a rule publication.

M9 implements optional local AI using strict protocol/quote-proof contracts and official
policy text only. No sponsor examples or prior user results were used. The official
Ollama runtime and qwen2.5:3b were later downloaded and checksum-verified for real local
validation. Five opt-in checks passed using official phrases and one literal instruction
atom. No narrative adversarial paper was generated. The main project's AI setting
remains disabled; real-model UI scans and configuration changes used only the isolated
QA root. CPU execution was required because Metal command queues were unavailable.

The user's subsequent layout request applies to both on-screen review and downloads.
It supersedes M7's default addition of review notes: highlights only is now the default,
with notes explicitly optional. The attached key files were not needed and remain
unopened. Mechanical visual QA uses only official phrases, a table, a solid image,
page breaks and orientation values. Policy wording, detectors and thresholds were
unchanged. Existing user runs and the user's running backend were left untouched.

M10 adds process-wide Python socket/DNS blocking, shared parser-worker counters, offline
observability, managed local startup and a clean bundle/installer. Packaging uses declared
application/model files and a sanitized current-policy baseline. It excludes user runs,
source documents, decisions, credentials, drafts and prior policy audit records. The
source audit history is not opened by packaging. Offline workflow fixtures contain only
official phrases, page/format atoms and reviewer metadata; no sponsor material is used.
Physical Wi-Fi-off and a separate target Mac remain external acceptance checks.
