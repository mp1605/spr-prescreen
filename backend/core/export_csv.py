"""Flat UTF-8 CSV: a row per finding, with explicit flagless/unfinished entry rows."""

from __future__ import annotations

import csv
import io
import json

from backend.core.export_models import ExportReport

COLUMNS = (
    "row_type",
    "run_id",
    "entry_id",
    "file_name",
    "phase",
    "entry_message",
    "source_sha256",
    "current_source_sha256",
    "source_integrity",
    "rules_version",
    "ai_state",
    "ai_configuration_json",
    "ai_evidence_json",
    "release_decision",
    "paper_color",
    "paper_label",
    "incomplete_reasons",
    "flag_total",
    "finding_id",
    "list",
    "items",
    "flag_color",
    "quote",
    "page",
    "paragraph",
    "char_start",
    "char_end",
    "reason",
    "why_unsure",
    "engines",
    "score",
    "color_assessment_json",
    "review_revision",
    "review_action",
    "reviewer",
    "review_utc",
    "review_reason",
    "source_inspected",
    "reviewer_approved",
    "approval_reviewer",
    "approval_utc",
    "organized_document_path",
    "document_storage_error",
    "source_inspection_history_json",
    "review_history_json",
    "generated_utc",
    "disclaimer",
)


def spreadsheet_safe(value: object) -> str:
    text = "" if value is None else str(value)
    # Quotes are not sufficient to stop a spreadsheet interpreting formula text.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def report_csv(report: ExportReport) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS)
    writer.writeheader()
    for entry in report.batch.entries:
        paper = entry.result
        review = report.reviews[entry.entry_id]
        common: dict[str, object] = {
            "run_id": report.batch.run_id,
            "entry_id": entry.entry_id,
            "file_name": entry.file_name,
            "phase": entry.phase,
            "entry_message": entry.message,
            "source_sha256": report.source_sha256[entry.entry_id],
            "current_source_sha256": report.current_source_sha256[entry.entry_id],
            "source_integrity": report.source_integrity[entry.entry_id],
            "rules_version": paper.rules_version if paper else report.batch.rules_version,
            "ai_state": paper.ai_state if paper else "not_run",
            "ai_configuration_json": paper.ai.model_dump_json() if paper and paper.ai else None,
            "release_decision": report.release_decision,
            "paper_color": paper.color if paper else None,
            "paper_label": paper.label if paper else None,
            "incomplete_reasons": " | ".join(paper.incomplete_reasons) if paper else None,
            "flag_total": paper.flag_count.total if paper else None,
            "review_revision": review.revision,
            "source_inspected": review.inspected,
            "reviewer_approved": review.approved,
            "approval_reviewer": review.approval_event.reviewer if review.approval_event else None,
            "approval_utc": review.approval_event.utc.isoformat()
            if review.approval_event
            else None,
            "organized_document_path": review.storage_file,
            "document_storage_error": review.storage_error,
            "source_inspection_history_json": json.dumps(
                [e.model_dump(mode="json") for e in review.events if e.finding_id is None],
                ensure_ascii=True,
            ),
            "generated_utc": report.generated_utc.isoformat(),
            "disclaimer": report.disclaimer,
        }
        for flag in paper.findings if paper and paper.findings else (None,):
            event = review.decisions.get(flag.finding_id) if flag else None
            row = common | {"row_type": "finding" if flag else "paper" if paper else "entry"}
            if flag:
                row.update(
                    {
                        "finding_id": flag.finding_id,
                        "ai_evidence_json": json.dumps(
                            [m.model_dump(mode="json") for m in flag.ai_matches], ensure_ascii=True
                        ),
                        "list": flag.list,
                        "items": " | ".join(flag.items),
                        "flag_color": flag.color,
                        "quote": flag.quote,
                        "page": flag.location.page,
                        "paragraph": flag.location.paragraph,
                        "char_start": flag.location.char_start,
                        "char_end": flag.location.char_end,
                        "reason": flag.reason,
                        "why_unsure": flag.why_unsure,
                        "engines": " | ".join(flag.engines),
                        "score": flag.score,
                        "color_assessment_json": flag.assessment.model_dump_json()
                        if flag.assessment
                        else None,
                    }
                )
            row.update(
                {
                    "review_action": event.action if event else "pending" if flag else None,
                    "reviewer": event.reviewer if event else None,
                    "review_utc": event.utc.isoformat() if event else None,
                    "review_reason": event.reason if event else None,
                    "review_history_json": json.dumps(
                        [
                            e.model_dump(mode="json")
                            for e in review.events
                            if e.finding_id == (flag.finding_id if flag else None)
                        ],
                        ensure_ascii=True,
                    ),
                }
            )
            writer.writerow({key: spreadsheet_safe(value) for key, value in row.items()})
    return output.getvalue()
