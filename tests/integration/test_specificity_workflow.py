import hashlib

from tests.integration.test_workflow import base_for, finished, upload, word


def test_fused_color_evidence_survives_review_and_readback(client, project_root):
    batch = finished(
        client,
        upload(
            client,
            [
                ("specificity-format.docx", word("F-22 · 3 aircraft · 7th Wing · readiness")),
                ("official-topic.docx", word("Unmanned aerial systems")),
            ],
        )["run_id"],
    )
    red, yellow = [entry["result"] for entry in batch["entries"]]
    assert red["color"] == "red" and yellow["color"] == "yellow"
    assert red["fusion"]["state"] == "complete"
    flag = next(f for f in red["findings"] if "L2-06" in f["items"])
    assert {"L2-06", "L2-12", "L2-14"} <= set(flag["items"])
    assert all(
        item["evidence"] and item["rule_anchor"]
        for item in flag["assessment"]["items"]
        if item["disposition"] == "clear"
    )
    snapshot = project_root / "runs" / batch["run_id"] / "results.json"
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    response = client.post(
        base_for(batch) + "/decisions",
        json={
            "reviewer": "Format QA",
            "revision": 0,
            "action": "override",
            "finding_id": flag["finding_id"],
        },
    )
    assert response.status_code == 200
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    assert client.get(base_for(batch)).json()["result"] == red


def test_real_pdf_fusion_keeps_word_rectangles_and_renderable_page(client):
    import fitz

    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 60), "F-22 | 3 aircraft | 7th Wing | readiness")
        data = pdf.tobytes()
    batch = finished(client, upload(client, [("specificity-format.pdf", data)])["run_id"])
    base = base_for(batch)
    result = batch["entries"][0]["result"]
    flag = next(f for f in result["findings"] if "L2-06" in f["items"])
    assert flag["color"] == "red" and flag["location"]["page"] == 1
    document = client.get(base + "/document").json()
    unit = document["units"][0]
    start, end = flag["location"]["char_start"], flag["location"]["char_end"]
    assert unit["text"][start:end] == flag["quote"]
    assert flag["location"]["bbox"] == [
        w["bbox"] for w in unit["words"] if w["char_start"] < end and start < w["char_end"]
    ]
    image = client.get(base + "/pages/1.png")
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
