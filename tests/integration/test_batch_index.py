"""The requested five-column schema uses live scanner output, never key results."""

import csv
import io

from tests.integration.test_workflow import finished, upload, word

COLUMNS = ["Paper", "File format", "Expected result", "# triggers", "Title"]


def test_batch_exports_have_exact_columns_and_actual_results(client, orthogonal_semantics):
    batch = finished(
        client,
        upload(
            client,
            [
                ("heading.docx", word("Document title")),
                ("flagged.docx", word("(CUI).")),
                ("broken.pdf", b"not PDF"),
                ("unsupported.txt", b"excluded"),
            ],
        )["run_id"],
    )
    base = f"/api/batches/{batch['run_id']}/export"
    response = client.get(base + "/json")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 4 and all(list(row) == COLUMNS for row in rows)
    assert rows[0] == {
        "Paper": "heading",
        "File format": "DOCX",
        "Expected result": "Green",
        "# triggers": 0,
        "Title": "Document title",
    }
    assert rows[1]["Expected result"] == "Red"
    assert rows[1]["# triggers"] == batch["entries"][1]["result"]["flag_count"]["total"]
    assert rows[2]["Expected result"] == "Yellow" and rows[2]["# triggers"] == 0
    assert rows[3]["Expected result"] == "Rejected" and rows[3]["# triggers"] is None
    response = client.get(base + "/csv")
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    assert reader.fieldnames == COLUMNS
    assert list(reader) == [
        {key: "" if value is None else str(value) for key, value in row.items()} for row in rows
    ]
    assert client.get(base + "/json?layout=audit").json()["schema_version"] == "spr-export-v1"


def test_cancelled_batch_has_no_fabricated_green_or_trigger_count(client, monkeypatch):
    monkeypatch.setattr(client.app.state.batch_service, "submit", lambda *args: None)
    batch = upload(client, [("pending.docx", word())])
    client.post(f"/api/batches/{batch['run_id']}/cancel")
    row = client.get(f"/api/batches/{batch['run_id']}/export/json").json()[0]
    assert row["Expected result"] == "Cancelled" and row["# triggers"] is None
