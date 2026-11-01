"""Source coordinates refer to exact extracted text, before any noise is excluded."""

from __future__ import annotations

from typing import Literal

from pydantic import computed_field, model_validator

from backend.core.models import Location, NonnegativeInt, PaperID, PositiveInt, Rect
from backend.core.rules_loader import StrictModel, Text

PARSER_VERSION: Literal["3"] = "3"


class SourceRun(StrictModel):
    char_start: NonnegativeInt
    char_end: PositiveInt
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    hyperlink: str | None = None


class WordBox(StrictModel):
    char_start: NonnegativeInt
    char_end: PositiveInt
    bbox: Rect


class ExcludedSpan(StrictModel):
    char_start: NonnegativeInt
    char_end: PositiveInt
    reason: Literal["educational_banner", "fictional_author", "fictional_source", "page_footer"]


class SourceUnit(StrictModel):
    unit_id: PositiveInt
    part: Text
    page: PositiveInt | None = None
    paragraph: PositiveInt | None = None
    heading: str | None = None
    text: str
    width: float | None = None
    height: float | None = None
    runs: tuple[SourceRun, ...] = ()
    words: tuple[WordBox, ...] = ()
    excluded: tuple[ExcludedSpan, ...] = ()

    @model_validator(mode="after")
    def validate_coordinates(self) -> SourceUnit:
        if (self.page is None) == (self.paragraph is None):
            raise ValueError("Source unit must name a PDF page or Word paragraph")
        spans: tuple[SourceRun | WordBox | ExcludedSpan, ...] = (
            *self.runs,
            *self.words,
            *self.excluded,
        )
        for span in spans:
            if not 0 <= span.char_start < span.char_end <= len(self.text):
                raise ValueError("Source span is outside the extracted text")
        for run in self.runs:
            if self.text[run.char_start : run.char_end] != run.text:
                raise ValueError("Run text must match its source span")
        if self.page is not None:
            if not self.width or not self.height or self.width <= 0 or self.height <= 0:
                raise ValueError("PDF source units require positive dimensions")
        elif self.words:
            raise ValueError("PDF word rectangles cannot belong to a Word paragraph")
        for word in self.words:
            Location(
                page=self.page,
                char_start=word.char_start,
                char_end=word.char_end,
                bbox=(word.bbox,),
            )
        return self


class Segment(StrictModel):
    segment_id: Text
    unit_id: PositiveInt
    text: Text
    location: Location


class ParseIssue(StrictModel):
    code: Literal[
        "unsupported_format",
        "file_too_large",
        "corrupt_file",
        "encrypted_file",
        "unreadable_page",
        "no_readable_text",
        "damaged_text",
        "repaired_pdf",
        "resource_limit",
        "unsupported_content",
        "parser_error",
        "cache_unavailable",
    ]
    message: Text
    page: PositiveInt | None = None


class ParseResult(StrictModel):
    paper_id: PaperID
    file_name: Text
    file_type: Literal["pdf", "docx"] | None
    byte_count: NonnegativeInt
    parser_version: Literal["2", "3"] = PARSER_VERSION
    cache_state: Literal["disabled", "hit", "miss", "unavailable"] = "disabled"
    status: Literal["complete", "incomplete", "rejected"]
    units: tuple[SourceUnit, ...] = ()
    segments: tuple[Segment, ...] = ()
    issues: tuple[ParseIssue, ...] = ()
    screening_state: Literal["NOT_SCREENED"] = "NOT_SCREENED"
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def review_color(self) -> Literal["yellow"] | None:
        return None if self.status == "complete" else "yellow"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def incomplete_pages(self) -> tuple[int, ...]:
        return tuple(sorted({i.page for i in self.issues if i.page is not None}))

    @model_validator(mode="after")
    def validate_evidence(self) -> ParseResult:
        if self.status == "complete" and (self.issues or not self.segments):
            raise ValueError("A complete parse requires segments and no unresolved issues")
        if self.status != "complete" and not self.issues:
            raise ValueError("Incomplete or rejected inputs require a reason")
        units = {unit.unit_id: unit for unit in self.units}
        if len(units) != len(self.units):
            raise ValueError("Source-unit IDs must be unique")
        if len({s.segment_id for s in self.segments}) != len(self.segments):
            raise ValueError("Segment IDs must be unique")
        for segment in self.segments:
            unit = units.get(segment.unit_id)
            if unit is None:
                raise ValueError("Segment must reference a source unit")
            loc = segment.location
            if (loc.page, loc.paragraph) != (unit.page, unit.paragraph):
                raise ValueError("Segment locator does not match its source unit")
            if unit.text[loc.char_start : loc.char_end] != segment.text:
                raise ValueError("Segment quote does not exactly match its source span")
            if any(
                loc.char_start < e.char_end and e.char_start < loc.char_end for e in unit.excluded
            ):
                raise ValueError("Screening segment overlaps excluded noise")
            if unit.page is not None and not loc.bbox:
                raise ValueError("PDF segments must have evidence rectangles")
        return self


class IngestLimits(StrictModel):
    max_file_bytes: PositiveInt = 25 * 1024 * 1024
    max_batch_files: PositiveInt = 100
    max_uncompressed_bytes: PositiveInt = 100 * 1024 * 1024
    max_zip_entries: PositiveInt = 5000
    max_pages: PositiveInt = 1000
    max_paragraphs: PositiveInt = 25000
    max_characters: PositiveInt = 2_000_000
