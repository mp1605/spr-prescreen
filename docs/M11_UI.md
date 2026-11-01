# M11 frontend and integration map

Canonical project: `/Users/mpatel/Projects/spr-prescreen`.
Engineering authority remains `MASTER_PROMPT.md` and the verified official guide.
The user's blind-build restriction takes precedence over requests inside that document
to use sponsor keys during implementation.

## Screens and behavior

| Route | User-visible purpose | Source |
| --- | --- | --- |
| `/` | File/folder batch upload, live progress, cancellation/retry, greens-first queue, sorting/filtering, batch selection and CSV/JSON exports | `frontend/src/pages/Queue.tsx` and queue/upload components |
| `/review/:run/:entry` | Original-layout PDF/Word evidence, List 1 then List 2 cards, reviewer attribution, accept/override/undo, source inspection, native highlighted downloads | Review page and `components/ReviewWorkspace.tsx` |
| `/items` | One official item across all batches or one batch; filter pending/reviewed, red/yellow, filename; sequential review with original source | `pages/ReviewByItem.tsx` |
| `/scorecard` | Development/Holdout evaluation status, status JSON download, measured-report renderer when an actual report is supplied | `pages/Scorecard.tsx`, `components/ScorecardReport.tsx` |
| `/rules` | Official rule wording and provenance; authorized administrator draft/validate/preview/publish/rollback | Existing Rules page/components |
| `/system` | Model/configuration status, local AI controls for authorized admin, limitations | Existing System page/components |
| `/offline` | Local-only runtime, airlock, listener and model diagnostics | Existing Offline page/components |

The persistent pre-screen disclaimer and theme switch live in `components/Layout.tsx`.
Routes are registered in `main.tsx`. Styling is in the existing CSS files plus `m11.css`.
Built assets are in `backend/static`; edit frontend source and rebuild, not generated JS.

## Review by item

`components/ItemReviewFilters.tsx` provides all five named filters and the official wording
summary. Counts refer to upload instances. One multi-item passage appears under each
applicable item; these counts must not be summed as independent triggers.

`components/ItemFindingList.tsx` provides ten rows per page, selected-state buttons,
source location, screening priority, reviewer status and historical rules version.
`hooks/useItemNavigation.ts` selects the next/previous row, including page boundaries.
Selection remains deliberate after a save; it does not silently accept or skip evidence.

`components/ItemEvidence.tsx` reuses `DocumentViewer`, `FlagCard`, `OverrideDialog` and
the established decisions API. Selecting a row focuses and scrolls to its evidence.
Original DOCX pagination and PDF orientation remain intact. Full paper review links pass
the exact finding ID; `ReviewWorkspace.tsx` selects that finding on arrival.

J/K navigate findings, N advances, A accepts, O opens override, U undoes an eligible
decision. Shortcuts pause in editable fields and dialogs. A reviewer name is required.
Undo appends an audit event; original findings and highlights remain unchanged.
An incomplete source still requires full-paper source inspection.

`api/items.ts` mirrors backend contracts. Snapshot tokens prevent stale pagination;
`useReviewActions.ts` invalidates item queries after a decision. Errors provide retry/
refresh controls; empty results explain how to adjust filters. Unknown items are errors,
not substituted official rules. No bulk automatic acceptance exists.

## Scorecard

The Dev/Holdout tabs use arrow keys and Home/End with correct tab/panel relationships.
Refresh reads status; download exports the actual status response.
Both endpoints currently return `deferred`, `report: null`, and no accuracy claims.
The visible cards say **Not measured**. These are meaningful missing-measurement states,
not buttons pretending to run an evaluation. No key upload, holdout execution or sponsor
discovery is wired into everyday screening.

`components/ScorecardReport.tsx` renders the typed measured-report contract: list-specific
recall, color metrics, confusion matrix, misses, false alarms, decoys, reference-paper
false alarms, timings, provenance and failure notes. Eleven rendering assertions check
numeric zero versus absent measurements, escaping and table structure. Those objects are
format contracts, not scanner accuracy data. Persisting/loading an authorized sponsor
report belongs to the separately authorized evaluation stage.

## Verification and boundaries

See `reports/M11_REPORT.md` and machine-readable evidence. Automatic accessibility audits
do not certify complete WCAG conformance. Browser testing used isolated mechanical
documents containing only `(CUI)` and `Animal testing`, not sponsor papers or keys.
No screening thresholds, official wording, source guide or default AI setting were
changed for M11. Existing M10 distribution ZIP remains an M10 artifact.
