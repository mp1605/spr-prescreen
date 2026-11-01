"""AI can enrich a baseline passage or add a new one, never replace baseline findings."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from backend.core.ai_quotes import VerifiedAI
from backend.core.color_models import ColorAssessment, ItemAssessment, SpecificityFeature
from backend.core.models import Finding, Location, PaperResult
from backend.core.policy import ListName
from backend.core.specificity_policy import CONDITIONS, JUDGMENT


def ai_assessment(match: VerifiedAI) -> ItemAssessment:
    evidence = match.evidence
    if evidence.item_id.startswith("L1-"):
        return ItemAssessment(
            item_id=evidence.item_id,
            disposition="clear",
            reason=evidence.reason,
            ai_evidence=evidence,
        )
    disposition: Literal["clear", "possible"] = "possible"
    proof: tuple[SpecificityFeature, ...] = ()
    anchor = None
    kinds = {fact.kind for fact in match.features}
    if (
        evidence.clear_or_possible == "clear"
        and evidence.item_id not in JUDGMENT
        and not kinds & {"uncertainty", "negation"}
    ):
        for condition in CONDITIONS[evidence.item_id]:
            if set(condition) <= kinds:
                proof = tuple(
                    next(f for f in match.features if f.kind == kind) for kind in condition
                )
                anchor = SpecificityFeature(
                    kind="topic",
                    text=evidence.quote,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                )
                disposition = "clear"
                break
    reason = evidence.reason + (
        " Specific source facts were checked against the item's specificity requirements."
        if disposition == "clear"
        else " Retained as possible: model assertions alone do not establish "
        "source specificity or judgment."
    )
    return ItemAssessment(
        item_id=evidence.item_id,
        disposition=disposition,
        reason=reason,
        evidence=proof,
        rule_anchor=anchor,
        ai_evidence=evidence,
    )


def merge_ai(
    baseline: PaperResult, verified: tuple[VerifiedAI, ...], profile: str
) -> tuple[Finding, ...]:
    flags = list(baseline.findings)
    for match in verified:
        segment, evidence = match.segment, match.evidence
        list_name: ListName = "list1" if evidence.item_id.startswith("L1-") else "list2"
        target = next(
            (
                index
                for index, flag in enumerate(flags)
                if flag.list == list_name
                and (flag.location.page, flag.location.paragraph)
                == (segment.location.page, segment.location.paragraph)
                and flag.location.char_start <= segment.location.char_start
                and segment.location.char_end <= flag.location.char_end
            ),
            None,
        )
        decision = ai_assessment(match)
        if target is None:
            identifier = hashlib.sha256(
                json.dumps(
                    [
                        baseline.paper_id,
                        baseline.rules_version,
                        profile,
                        list_name,
                        segment.segment_id,
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            loc = segment.location
            flag = Finding(
                finding_id="finding:ai:" + identifier,
                paper_id=baseline.paper_id,
                list=list_name,
                items=(evidence.item_id,),
                color="red" if decision.disposition == "clear" else "yellow",
                quote=segment.text,
                location=Location(**loc.model_dump()),
                reason="Local AI suggestion with verified source evidence; "
                "reviewer applicability check required.",
                why_unsure=decision.reason if decision.disposition == "possible" else None,
                engines=("ai",),
                assessment=ColorAssessment(items=(decision,)),
                ai_matches=(evidence,),
            )
            flags.append(flag)
            continue
        old = flags[target]
        decisions = {item.item_id: item for item in old.assessment.items} if old.assessment else {}
        # Diagnostic baseline findings can omit assessments; preserve their established colors.
        if not old.assessment:
            decisions = {
                item: ItemAssessment(
                    item_id=item,
                    disposition="clear" if old.list == "list1" else "possible",
                    reason=old.reason,
                )
                for item in old.items
            }
        previous = decisions.get(evidence.item_id)
        if previous is None or previous.disposition != "clear":
            decisions[evidence.item_id] = decision
        color = (
            "red"
            if old.color == "red" or any(d.disposition == "clear" for d in decisions.values())
            else "yellow"
        )
        uncertainty = old.why_unsure or (
            decision.reason if decision.disposition == "possible" else None
        )
        flags[target] = Finding.model_validate(
            old.model_dump()
            | {
                "items": tuple(sorted(set(old.items) | {evidence.item_id})),
                "engines": tuple(
                    name for name in ("rules", "semantic", "ai") if name in (*old.engines, "ai")
                ),
                "color": color,
                "assessment": ColorAssessment(
                    items=tuple(decisions[item] for item in sorted(decisions))
                ),
                "ai_matches": (*old.ai_matches, evidence),
                "why_unsure": uncertainty,
                "reason": old.reason
                + (
                    " Local AI proposes higher review priority; "
                    "inspect its verified quote and reason."
                    if color != old.color
                    else ""
                ),
            }
        )
    result = tuple(
        sorted(
            flags,
            key=lambda flag: (
                flag.list,
                flag.location.page or flag.location.paragraph or 0,
                flag.location.char_start,
                flag.finding_id,
            ),
        )
    )
    # Enforce the add-only invariant independently of the model and merge implementation.
    by_id = {flag.finding_id: flag for flag in result}
    for old in baseline.findings:
        current = by_id.get(old.finding_id)
        if (
            current is None
            or not set(old.items) <= set(current.items)
            or not set(old.engines) <= set(current.engines)
        ):
            raise ValueError("AI merge attempted to remove baseline evidence")
        if old.color == "red" and current.color != "red":
            raise ValueError("AI merge attempted a downgrade")
        if old.quote != current.quote or old.location != current.location:
            raise ValueError("AI merge attempted to move baseline evidence")
    return result
