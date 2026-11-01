"""Human-readable annotation notes retain raw screening priority and review provenance."""

from __future__ import annotations

from backend.core.batch_models import ReviewState
from backend.core.models import Finding, PaperResult
from backend.core.policy import DISCLAIMER


class AnnotationError(ValueError):
    """A source cannot be annotated faithfully; callers should expose the reason."""


def overridden(flag: Finding, review: ReviewState) -> bool:
    decision = review.decisions.get(flag.finding_id)
    return decision is not None and decision.action == "override"


def summary_note(paper: PaperResult, review: ReviewState) -> str:
    return "\n".join(
        [
            "SPR annotated review copy",
            DISCLAIMER,
            f"Original SHA-256: {paper.paper_id.removeprefix('sha256:')}",
            f"Rules: {paper.rules_version} | AI: {paper.ai_state}",
            f"Raw screening: {paper.color.upper()} | Flags: {paper.flag_count.total}",
            f"Review snapshot: revision {review.revision} | Source inspected: {review.inspected}",
            "Pending and accepted findings retain red/yellow highlights. "
            "Overridden highlights are removed; decisions remain in notes and audit history.",
            "Release decision: NOT_MADE_BY_TOOL",
            *(
                ["Incomplete: " + "; ".join(paper.incomplete_reasons)]
                if paper.incomplete_reasons
                else []
            ),
        ]
    )


def finding_note(flag: Finding, paper: PaperResult, review: ReviewState) -> str:
    decision = review.decisions.get(flag.finding_id)
    lines = [
        f"{flag.color.upper()} | {flag.list} | {', '.join(flag.items)}",
        flag.reason,
        *(["Why unsure: " + flag.why_unsure] if flag.why_unsure else []),
        f"Source: page {flag.location.page}"
        if flag.location.page
        else f"Source: paragraph {flag.location.paragraph}",
        f"Evidence: {flag.quote}",
        f"Engines: {', '.join(flag.engines)}",
        f"Finding: {flag.finding_id}",
        f"Rules: {paper.rules_version} | AI: {paper.ai_state}",
    ]
    for evidence in flag.ai_matches:
        lines.extend(
            [
                "Local AI suggestion: " + evidence.clear_or_possible,
                "AI verified source quote: " + evidence.quote,
                "AI reason: " + evidence.reason,
            ]
        )
    if decision:
        lines.append(
            f"Reviewer decision: {decision.action} | {decision.reviewer} | "
            f"{decision.utc.isoformat()}"
        )
        if decision.reason:
            lines.append("Reviewer reason: " + decision.reason)
        if decision.action == "override":
            lines.append("Highlight removed by reviewer override; raw finding retained in audit.")
    else:
        lines.append("Reviewer decision: pending")
    lines.extend([f"Review snapshot: revision {review.revision}", DISCLAIMER])
    return "\n".join(lines)
