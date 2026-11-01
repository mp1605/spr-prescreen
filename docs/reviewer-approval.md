# Reviewed document folders

Each newly processed batch creates local folders beneath:

`/Users/mpatel/Projects/spr-prescreen/runs/Batch Documents/<date>_<time-AM-or-PM>_<file-count>/`

For example: `2026-11-01_06-15-30-AM_12-files`. Times use America/Chicago, including daylight saving time. The count includes every file submitted in that batch. If batches share the same second and file count, a readable `Batch-2` suffix keeps them separate. Existing ID-named folders are renamed automatically when the updated app starts; internal batch IDs and source/audit paths stay unchanged. The manifest links each readable folder to its internal batch ID.

- **Pending Review**: green documents awaiting explicit human approval; retained failed/cancelled uploads awaiting further action.
- **Flagged**: all red and yellow documents together, including incomplete documents. Accepting or overriding flags does not move these into Approved.
- **Approved**: complete green documents for which a reviewer entered their name and clicked **Mark reviewed & approve**.

Flagged documents are saved as highlighted review copies in their original PDF/DOCX format and layout. Pending and accepted flags retain their red/yellow highlights. Overriding a flag removes its highlight and records the reviewer decision in a comment; Undo restores the highlight. Folder copies update after each saved decision. A numbered prefix prevents duplicate names from overwriting each other. Green documents keep their original bytes. The scanner's private originals, raw findings, and original color remain preserved.

Existing managed copies are upgraded from saved findings and decisions on app restart or through Update batch folders; this does not rerun screening or Ollama. The manifest records source and generated-file checksums, review revision and renderer version. Modified copies are preserved and reported rather than overwritten. Unreadable/signed documents that cannot be annotated retain an original copy with an explicit storage message requiring manual review.

Approval records the reviewer, UTC timestamp, revision and event ID in the append-only review history and batch manifest. JSON and CSV reports also include human approval status. Approval is the reviewer's action; the scanner does not make a release decision automatically. Reviewer names are local audit labels, not authenticated identities.

**Undo** by the same reviewer returns an approved copy to Pending Review and retains both audit events. Revision checks prevent overwriting a decision made in another window.

Expand **Batch document folders** in the queue to see the exact local path and counts. In Finder, use Command+Shift+G and paste the path. **Create/Update batch folders** also organizes an existing batch without rescanning it or changing its review history.

If copying fails after an approval was recorded, the UI explicitly reports that the review was saved but storage needs updating. After fixing disk permissions/space, use Update batch folders. Modified copies and symbolic links are refused rather than overwritten. Folder projection is recoverable from retained originals and review history; do not edit managed copies in place.
