"""Exercise real harness functions without reading sponsor artifacts or running detectors."""

from __future__ import annotations

from typing import Literal

from backend.core.rules_loader import RuleRegistry
from backend.eval.contracts import docx_format_contract, metric_contract, pdf_format_contract
from backend.eval.matching import match_passages
from backend.eval.models import GoldCase, Passage, PredictionCase
from backend.eval.parse_keys import parse_key_bytes
from backend.eval.report import render_report
from backend.eval.score import score_cases
from backend.eval.split import case_ids


def run_self_check(registry: RuleRegistry) -> dict[str, object]:
    checks: list[str] = []
    formats: tuple[tuple[Literal["docx", "pdf"], bytes], ...] = (
        ("docx", docx_format_contract(registry)),
        ("pdf", pdf_format_contract(registry)),
    )
    for kind, data in formats:
        parsed = parse_key_bytes(data, kind, case_id=f"format-contract-{kind}", registry=registry)
        if (
            len(parsed.triggers) != 1
            or parsed.triggers[0].quote != registry.list2[0].text
            or parsed.decoys != (registry.list2[1].text,)
        ):
            raise ValueError("Key format self-check did not preserve its contract data")
        checks.append(f"{kind} bold/tag/table/decoy format")
    gold, prediction = metric_contract(registry)
    report = score_cases((gold,), (prediction,), kind="format_contract")
    if report.trigger_recall != 1 or report.list1_recall is not None or report.weighted_cost != 0:
        raise ValueError("Metric arithmetic self-check failed")
    checks.append("known metric arithmetic and undefined denominators")
    narrow = Passage(
        finding_ids=("narrow",), quote=gold.triggers[0].quote, items=("L2-01",), color="yellow"
    )
    broad = narrow.model_copy(update={"finding_ids": ("broad",), "items": ("L2-01", "L2-02")})
    second = gold.triggers[0].model_copy(update={"tag": "T2", "items": ("L2-02",)})
    if len(match_passages((broad, narrow), (gold.triggers[0], second))) != 2:
        raise ValueError("Maximum one-to-one assignment self-check failed")
    checks.append("maximum-cardinality one-to-one matching")
    blank = prediction.result.model_copy(
        update=dict(
            color="green",
            label="No flags found",
            findings=(),
            flag_count=prediction.result.flag_count.model_copy(update=dict(total=0, yellow=0)),
        )
    )
    no_triggers = score_cases(
        (GoldCase(case_id="empty-contract", expected_color="green"),),
        (PredictionCase(case_id="empty-contract", result=blank),),
        kind="format_contract",
    )
    if no_triggers.trigger_recall is not None or "Not defined" not in render_report(no_triggers):
        raise ValueError("Empty-denominator report self-check failed")
    checks.append("honest report rendering")
    dev, holdout = set(case_ids("dev")), set(case_ids("holdout"))
    if len(dev) != 60 or len(holdout) != 20 or dev & holdout:
        raise ValueError("Frozen split metadata self-check failed")
    checks.append("frozen 60/20 split metadata")
    return dict(
        kind="harness_self_check",
        scanner_accuracy_measured=False,
        sponsor_files_accessed=False,
        checks_passed=len(checks),
        checks=checks,
    )
