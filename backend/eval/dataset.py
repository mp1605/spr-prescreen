"""Explicit evaluation sources; gold interpretation never enters the scanner."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.core.ingest import DocumentInput
from backend.core.rules_loader import RuleRegistry
from backend.eval.key_format import KeyTable
from backend.eval.models import GoldCase
from backend.eval.parse_keys import parse_blocks
from backend.eval.read_docx import read_docx
from backend.eval.read_pdf import read_pdf
from backend.eval.split import case_ids


@dataclass(frozen=True)
class EvaluationDataset:
    gold: tuple[GoldCase, ...]
    papers: tuple[DocumentInput, ...]
    inventory: tuple[dict[str, str], ...]
    ignored_keys: tuple[str, ...]


def canonical_files(directory: Path, *, keys: bool) -> dict[str, Path]:
    pattern = r"(SPR-Test-\d{3})" + (r"_KEY" if keys else "") + r"\.(docx|pdf)"
    files: dict[str, Path] = {}
    for path in directory.iterdir():
        match = re.fullmatch(pattern, path.name)
        if not match or not path.is_file():
            continue
        if match[1] in files:
            raise ValueError("Duplicate canonical case identity in evaluation sources")
        files[match[1]] = path
    expected = set(case_ids("dev")) | set(case_ids("holdout"))
    if files.keys() != expected:
        raise ValueError("Evaluation needs exactly the canonical 80 papers and 80 keys")
    return files


def load_dataset(
    paper_directory: Path,
    key_directory: Path,
    crosswalk: Path,
    registry: RuleRegistry,
) -> EvaluationDataset:
    papers, keys = (
        canonical_files(paper_directory, keys=False),
        canonical_files(key_directory, keys=True),
    )
    mapping = {
        entry["reference"]: tuple(entry["items"])
        for entry in json.loads(crosswalk.read_text())["references"]
    }
    gold: list[GoldCase] = []
    inputs: list[DocumentInput] = []
    inventory: list[dict[str, str]] = []
    for case_id in sorted(papers):
        paper, key = papers[case_id], keys[case_id]
        data, key_data = paper.read_bytes(), key.read_bytes()
        blocks = read_docx(key_data) if key.suffix == ".docx" else read_pdf(key_data)
        remapped = []
        for block in blocks:
            if isinstance(block, KeyTable):
                rows = []
                for row in block.rows:
                    if len(row) == 4 and re.fullmatch(r"T\d+", row[0].strip()):
                        if row[1] not in mapping:
                            raise ValueError("Answer reference missing from reviewed crosswalk")
                        row = (row[0], "; ".join(mapping[row[1]]), *row[2:])
                    rows.append(row)
                block = KeyTable(tuple(rows), block.paragraphs)
            remapped.append(block)
        case = parse_blocks(
            tuple(remapped),
            case_id=case_id,
            registry=registry,
            source_sha256=hashlib.sha256(key_data).hexdigest(),
        )
        paper_hash = hashlib.sha256(data).hexdigest()
        gold.append(case.model_copy(update={"paper_id": "sha256:" + paper_hash}))
        inputs.append(DocumentInput(paper.name, data))
        inventory.append(
            dict(
                case_id=case_id,
                file_name=paper.name,
                paper_sha256=paper_hash,
                key_name=key.name,
                key_sha256=hashlib.sha256(key_data).hexdigest(),
            )
        )
    if sum(len(case.triggers) for case in gold) != 99:
        raise ValueError("Parsed trigger total differs from the specification's 99; review keys")
    ignored = tuple(sorted(p.name for p in key_directory.iterdir() if p not in keys.values()))
    return EvaluationDataset(tuple(gold), tuple(inputs), tuple(inventory), ignored)


def select_gold(
    dataset: EvaluationDataset, split: Literal["dev", "holdout"]
) -> tuple[GoldCase, ...]:
    selected = set(case_ids(split))
    return tuple(case for case in dataset.gold if case.case_id in selected)
