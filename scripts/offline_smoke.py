"""Exercise an isolated offline workflow using official phrases and format atoms only."""

import argparse
import hashlib
import io
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.runtime import configure_offline_environment  # noqa: E402

configure_offline_environment(ROOT)

import pymupdf  # noqa: E402
import yaml  # noqa: E402
from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.core.settings import load_settings  # noqa: E402
from backend.security.airlock import airlock_status  # noqa: E402


def run():
    start_count = airlock_status()[1]
    with tempfile.TemporaryDirectory(prefix="spr-offline-smoke-") as temporary:
        root = Path(temporary)
        for directory in ("config", "policies", "docs", "backend"):
            (root / directory).mkdir()
        for name in ("models", "runtime"):
            (root / name).symlink_to(ROOT / name, target_is_directory=True)
        (root / "backend/static").symlink_to(ROOT / "backend/static", target_is_directory=True)
        for name in (
            "docs/official-lists.pdf",
            "docs/policy-baseline.json",
            "policies/official_rules.yaml",
        ):
            shutil.copyfile(ROOT / name, root / name)
        rules = yaml.safe_load((root / "policies/official_rules.yaml").read_bytes())
        digest = hashlib.sha256((root / "policies/official_rules.yaml").read_bytes()).hexdigest()
        (root / "policies/active.json").write_text(
            json.dumps(
                {
                    "version": rules["policy_version"],
                    "sha256": digest,
                    "published_by": "Isolated offline format check",
                    "utc": "2026-10-31T00:00:00+00:00",
                    "change_note": "Official phrase and mechanical format checks only.",
                }
            )
        )
        settings = load_settings(ROOT).model_dump()
        settings["ai"].update(enabled=False, model_digest=None)
        (root / "config/settings.yaml").write_text(yaml.safe_dump(settings))
        word = Document()
        word.add_paragraph("Animal testing")
        buffer = io.BytesIO()
        word.save(buffer)
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=400, height=250)
            page.insert_text((30, 60), "(CUI)")
            page.set_rotation(90)
            data = pdf.tobytes()
        sources = [buffer.getvalue(), data]
        with TestClient(create_app(root), base_url="http://127.0.0.1") as client:
            response = client.post(
                "/api/batches",
                files=[
                    ("files", ("offline-format.docx", sources[0])),
                    ("files", ("offline-format.pdf", sources[1])),
                ],
            )
            assert response.status_code == 202, response.text
            run_id = response.json()["run_id"]
            for _ in range(300):
                batch = client.get("/api/batches/" + run_id).json()
                if all(e["phase"] == "done" for e in batch["entries"]):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Offline batch did not finish in 30 seconds")
            for index, entry in enumerate(batch["entries"]):
                result = entry["result"]
                assert result["trace"] == ["list1:done", "list2:done"]
                assert result["semantic"]["state"] == "complete"
                assert (
                    result["release_decision"] == "NOT_MADE_BY_TOOL" and result["ai_state"] == "off"
                )
                base = f"/api/batches/{run_id}/papers/{entry['entry_id']}"
                assert client.get(base + "/original").content == sources[index]
                flag = result["findings"][0]
                decision = client.post(
                    base + "/decisions",
                    json={
                        "action": "accept",
                        "revision": 0,
                        "reviewer": "Offline format check",
                        "finding_id": flag["finding_id"],
                    },
                )
                assert decision.status_code == 200
                assert client.get(base).json()["result"] == result
                copy = client.get(base + "/annotated")
                assert copy.status_code == 200, copy.text[:100]
                if index == 0:
                    assert Document(io.BytesIO(copy.content)).paragraphs[0].text == "Animal testing"
                    layout = client.get(base + "/layout")
                    assert layout.status_code == 200, layout.text
                    layout = layout.json()
                    assert len(layout["units"]) == 1 and layout["anchors"]
                    assert client.get(
                        base + "/layout/" + layout["identity"] + "/pages/1.png"
                    ).content.startswith(b"\x89PNG")
                else:
                    assert client.get(base + "/document").json()["page_rotations"] == {"1": 90}
                    assert client.get(base + "/pages/1.png").content.startswith(b"\x89PNG")
                    with pymupdf.open(stream=copy.content, filetype="pdf") as pdf:
                        assert pdf[0].rotation == 90
            for format in ("csv", "json"):
                response = client.get(f"/api/batches/{run_id}/export/{format}")
                assert response.status_code == 200 and response.content
            state = client.get("/api/system/offline").json()
            assert state["airlock_installed"] and state["models_on_disk"]["ready"]
    blocked = airlock_status()[1] - start_count
    assert blocked == 0, "Unexpected network attempts were blocked during the workflow"
    return {
        "workflow": "passed",
        "documents": 2,
        "semantic": "complete",
        "word_page_preview": "passed",
        "rotated_pdf": "passed",
        "review_and_exports": "passed",
        "blocked_calls_during_workflow": blocked,
        "sys_prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "test_scope": "official phrases and format atoms; no sponsor data",
        "physical_wifi_state": "not_measured",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    result = run()
    text = json.dumps(result, indent=2) + "\n"
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(text)
    print(text)
