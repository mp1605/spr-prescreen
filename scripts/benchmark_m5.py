"""Measure official-text format fixtures only. This is NOT sponsor evaluation.

Run from the project root: .venv/bin/python -m scripts.benchmark_m5
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path
from time import perf_counter

import pymupdf
from docx import Document

from backend.cli_io import write_report
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import DocumentInput, parse_many
from backend.core.rules_loader import load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.screen import screen_document
from backend.core.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    configure_offline_environment(ROOT)
    rules, settings = load_rules(ROOT), load_settings(ROOT)
    guide = (ROOT / "docs/official-lists.pdf").read_bytes()
    inputs: list[DocumentInput] = []
    for index in range(40):
        word = Document()
        word.core_properties.identifier = f"M5 official-format container {index}"
        for item in (*rules.list1, *rules.list2):
            word.add_paragraph(item.text)
        buffer = io.BytesIO()
        word.save(buffer)
        inputs.append(DocumentInput(f"official-format-{index:02}.docx", buffer.getvalue()))
        with pymupdf.open(stream=guide, filetype="pdf") as pdf:
            pdf.set_metadata(
                {"title": "Official policy guide", "subject": f"M5 format container {index}"}
            )
            inputs.append(DocumentInput(f"official-guide-{index:02}.pdf", pdf.tobytes()))
    assert len({hashlib.sha256(value.data).hexdigest() for value in inputs}) == 80
    with tempfile.TemporaryDirectory(prefix="spr-m5-benchmark-") as temporary:
        work = Path(temporary)
        started = perf_counter()
        parsed = parse_many(inputs, cache_directory=work / "parse", workers=2)
        parse_seconds = perf_counter() - started
        assert all(document.status == "complete" for document in parsed)
        print(f"Parsed {len(parsed)} official-format inputs in {parse_seconds:.3f}s", flush=True)
        engine = RulesEngine(rules)
        started = perf_counter()
        baseline = [screen_document(document, rules, engine=engine) for document in parsed]
        e1_seconds = perf_counter() - started
        started = perf_counter()
        provider = LocalBGE(ROOT)
        model_setup = perf_counter() - started
        semantic = SemanticEngine(work, rules, settings.semantic, provider=provider)
        started = perf_counter()
        results = []
        for index, document in enumerate(parsed):
            results.append(
                screen_document(document, rules, engine=engine, semantic=semantic.session())
            )
            if (index + 1) % 5 == 0:
                print(
                    f"Rules + semantic: {index + 1}/80 · {perf_counter() - started:.3f}s",
                    flush=True,
                )
        cold_seconds = perf_counter() - started
        assert all(result.semantic and result.semantic.state == "complete" for result in results)
        started = perf_counter()
        warm = [
            screen_document(document, rules, engine=engine, semantic=semantic.session())
            for document in parsed
        ]
        warm_seconds = perf_counter() - started
        assert all(one.findings == two.findings for one, two in zip(results, warm, strict=True))
        payload = {
            "milestone": "M5",
            "purpose": "official-text format throughput, not sponsor evaluation",
            "inputs": {
                "count": 80,
                "distinct_container_hashes": 80,
                "docx": 40,
                "pdf": 40,
                "content": (
                    "Official item texts and unchanged official guide pages only; "
                    "container metadata varies"
                ),
            },
            "timing_seconds": {
                "parse_process_pool": parse_seconds,
                "model_initialization": model_setup,
                "rules_only": e1_seconds,
                "rules_semantic_cold_vectors": cold_seconds,
                "rules_semantic_warm_vectors": warm_seconds,
                "parse_plus_model_plus_rules_semantic": parse_seconds + model_setup + cold_seconds,
                "cold_screening_per_input": cold_seconds / 80,
            },
            "timing_scope": (
                "Fixture construction and report writing excluded; model startup reported "
                "separately; cold stage includes reference embedding"
            ),
            "semantic": {
                "model_digest": provider.identity,
                "references": 39,
                "reference_digest": semantic.reference_digest,
                **settings.semantic.model_dump(mode="json"),
            },
            "vector_cache": {
                "cold_misses": sum(result.semantic.cache_state == "miss" for result in results),
                "warm_hits": sum(result.semantic.cache_state == "hit" for result in warm),
            },
            "flags": {
                "rules_only": sum(p.flag_count.total for p in baseline),
                "rules_semantic": sum(p.flag_count.total for p in results),
            },
            "rules_version": rules.policy_version,
            "sponsor_material_access": False,
            "sponsor_accuracy": None,
            "release_decision": "NOT_MADE_BY_TOOL",
            "limitations": [
                "Repeated official content is not representative of 80 distinct papers.",
                "Uncalibrated thresholds unchanged; throughput is not recall or false alarms.",
            ],
        }
        write_report(ROOT / "reports/M5-benchmark.json", payload)
        print(f"Completed: cold {cold_seconds:.3f}s; warm {warm_seconds:.3f}s", flush=True)


if __name__ == "__main__":
    main()
