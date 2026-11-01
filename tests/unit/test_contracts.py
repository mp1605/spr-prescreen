from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.core.models import Decision, Finding, FlagCount, Location, PaperResult

PAPER = "sha256:" + "a" * 64


def finding(**changes):
    data = dict(
        finding_id="finding-1",
        paper_id=PAPER,
        list="list1",
        items=["L1-1"],
        color="red",
        quote="Anything classified for national defense or foreign policy reasons",
        location=dict(page=1, char_start=0, char_end=74),
        reason="Official item reference",
        engines=["rules"],
    )
    data.update(changes)
    return Finding.model_validate(data)


def result(**changes):
    data = dict(
        paper_id=PAPER,
        file_name="contract.pdf",
        file_type="pdf",
        color="red",
        label="Flag identified",
        flag_count=dict(total=1, red=1, yellow=0),
        lists_checked=["list1", "list2"],
        trace=["list1:done", "list2:done"],
        ai_state="off",
        rules_version="v1",
        seconds=0.1,
        findings=[finding()],
    )
    data.update(changes)
    return PaperResult.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("items", []),
        ("items", ["L1-2"]),
        ("items", ["L2-01"]),
        ("items", ["L1-1", "L1-1"]),
        ("quote", ""),
        ("quote", "   "),
        ("location", None),
        ("engines", []),
        ("score", 1.5),
        ("color", "yellow"),
        ("paper_id", "filename.pdf"),
    ],
)
def test_invalid_findings_rejected(field, value):
    with pytest.raises(ValidationError):
        finding(**{field: value})


def test_yellow_requires_reason():
    with pytest.raises(ValidationError, match="why_unsure"):
        finding(list="list2", items=["L2-01"], color="yellow")
    assert finding(list="list2", items=["L2-01"], color="yellow", why_unsure="Needs judgment")


@pytest.mark.parametrize(
    "changes",
    [
        dict(page=None),
        dict(page=0),
        dict(paragraph=1),
        dict(char_end=0),
        dict(char_start=12, char_end=12),
        dict(bbox=[[5, 5, 1, 1]]),
    ],
)
def test_invalid_evidence_location_rejected(changes):
    with pytest.raises(ValidationError):
        Location.model_validate(dict(page=1, char_start=0, char_end=10) | changes)


def test_word_location():
    location = Location(paragraph=1, char_start=0, char_end=10)
    assert location.page is None


def test_raw_findings_are_deeply_immutable():
    raw = finding()
    before = raw.model_dump_json()
    Decision(
        finding_id=raw.finding_id, action="override", reviewer="Reviewer", utc=datetime.now(UTC)
    )
    assert raw.model_dump_json() == before
    assert isinstance(raw.items, tuple)
    with pytest.raises(ValidationError):
        raw.color = "yellow"
    with pytest.raises(ValidationError):
        raw.location.char_start = 2


@pytest.mark.parametrize(
    "changes",
    [
        dict(release_decision="APPROVED"),
        dict(color="green"),
        dict(label="No flags found"),
        dict(flag_count=dict(total=0, red=0, yellow=0)),
        dict(lists_checked=["list1"]),
        dict(trace=["list2:done", "list1:done"]),
        dict(paper_id="sha256:" + "b" * 64),
    ],
)
def test_inconsistent_results_rejected(changes):
    with pytest.raises(ValidationError):
        result(**changes)


def test_uncertainty_prevents_green():
    clean = dict(findings=[], flag_count=dict(total=0, red=0, yellow=0))
    assert result(**clean, color="green", label="No flags found")
    with pytest.raises(ValidationError, match="worst finding or uncertainty"):
        result(**clean, color="green", label="No flags found", incomplete_pages=[2])
    assert result(**clean, color="yellow", label="Incomplete", incomplete_reasons=["Unreadable"])
    assert result(**clean, color="yellow", label="Potential flag", ai_state="timeout")


def test_worst_color_and_total():
    flags = [finding()]
    for n in range(3):
        flags.append(
            finding(
                finding_id=f"yellow-{n}",
                list="list2",
                items=["L2-01"],
                color="yellow",
                why_unsure="Needs judgment",
            )
        )
    assert result(findings=flags, flag_count=dict(total=4, red=1, yellow=3)).color == "red"
    with pytest.raises(ValidationError):
        FlagCount(total=2, red=1, yellow=0)


def test_decisions_require_utc_and_reviewer():
    with pytest.raises(ValidationError):
        Decision(finding_id="1", action="accept", reviewer="", utc=datetime.now(UTC))
    with pytest.raises(ValidationError):
        Decision(finding_id="1", action="accept", reviewer="Reviewer", utc=datetime(2026, 10, 31))
