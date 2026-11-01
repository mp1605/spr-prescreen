"""Five-column batch summary; values come solely from the current scanner batch."""

import csv
import io
from pathlib import Path

from backend.core.export_csv import spreadsheet_safe
from backend.core.run_store import RunStore

COLUMNS = ("Paper", "File format", "Expected result", "# triggers", "Title")


def index_rows(store: RunStore, run_id: str) -> list[dict[str, str | int | None]]:
    rows: list[dict[str, str | int | None]] = []
    with store.lock:
        for entry in store.read(run_id).entries:
            paper = entry.result
            title = Path(entry.file_name).stem
            if paper:
                try:
                    parsed = store.parsed(run_id, entry.entry_id)
                    for unit in parsed.units:
                        if unit.paragraph is not None and unit.part != "word/document.xml":
                            continue
                        text = unit.text
                        for excluded in sorted(
                            unit.excluded, key=lambda span: span.char_start, reverse=True
                        ):
                            text = text[: excluded.char_start] + text[excluded.char_end :]
                        lines = [line.strip() for line in text.splitlines() if line.strip()]
                        if lines:
                            title = lines[0]
                            break
                except (OSError, ValueError):
                    pass  # Retained result remains exportable without a text cache.
            rows.append(
                dict(
                    zip(
                        COLUMNS,
                        (
                            Path(entry.file_name).stem,
                            paper.file_type.upper()
                            if paper
                            else Path(entry.file_name).suffix.lstrip(".").upper(),
                            paper.color.capitalize()
                            if paper and entry.phase == "done"
                            else entry.phase.capitalize(),
                            paper.flag_count.total if paper and entry.phase == "done" else None,
                            title,
                        ),
                        strict=True,
                    )
                )
            )
    return rows


def index_csv(rows: list[dict[str, str | int | None]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows({key: spreadsheet_safe(value) for key, value in row.items()} for row in rows)
    return output.getvalue()
