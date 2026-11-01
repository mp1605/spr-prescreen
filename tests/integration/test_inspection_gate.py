"""Inspection requires current decisions for every source-bound flag."""

import pytest

from tests.integration.test_workflow import base_for, finished, upload, word


@pytest.mark.parametrize(
    "text,color", [("(CUI). Animal testing.", "red"), ("Animal testing.", "yellow")]
)
def test_inspect_requires_every_flag_and_undo_reopens_review(
    client, orthogonal_semantics, text, color
):
    batch = finished(client, upload(client, [("official-atoms.docx", word(text))])["run_id"])
    paper = batch["entries"][0]["result"]
    assert paper["color"] == color and paper["findings"]
    base = base_for(batch)

    def command(action, revision, **extra):
        return client.post(
            base + "/decisions",
            json={"action": action, "reviewer": "QA", "revision": revision, **extra},
        )

    assert command("inspect", 0).status_code == 409
    assert client.get(base + "/decisions").json()["revision"] == 0
    last = None
    for revision, flag in enumerate(paper["findings"]):
        assert command("inspect", revision).status_code == 409
        response = command(
            "accept" if revision % 2 == 0 else "override",
            revision,
            finding_id=flag["finding_id"],
            reason="Manual inspection contract",
        )
        assert response.status_code == 200
        last = response.json()["decisions"][flag["finding_id"]]
    revision = len(paper["findings"])
    state = command("inspect", revision).json()
    assert state["inspected"] and not state["approved"]
    assert (
        command(
            "undo", revision + 1, finding_id=last["finding_id"], target_event=last["event_id"]
        ).status_code
        == 200
    )
    state = client.get(base + "/decisions").json()
    assert not state["inspected"]
    assert command("inspect", state["revision"]).status_code == 409
    progress = client.get("/api/batches").json()[0]["reviews"][batch["entries"][0]["entry_id"]]
    assert not progress["complete"]
