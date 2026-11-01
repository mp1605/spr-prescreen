"""Only duplicate, non-substantive List 2 headings yield to nearby body evidence."""

from backend.core.engines.base import Hit
from backend.core.evidence_heads import substantive_hits


def test_duplicate_heading_prefers_body_but_standalone_topic_survives(atom_document):
    doc = atom_document(
        "Drones",
        "Drones were tested with cameras along the perimeter "
        "during the recent flight trial by the operational unit.",
    )
    hits = tuple(
        Hit(
            segment_id=s.segment_id,
            item_id="L2-04",
            list="list2",
            detector="Atomic topic",
            char_start=s.location.char_start,
            char_end=s.location.char_start + 6,
        )
        for s in doc.segments
    )
    assert substantive_hits(hits, doc) == (hits[1],)
    assert substantive_hits((hits[0],), doc) == (hits[0],)


def test_list1_evidence_is_never_suppressed(atom_document):
    doc = atom_document(
        "Secret",
        "Secret information is described in this very long paragraph "
        "with additional details that require human inspection.",
    )
    hits = tuple(
        Hit(
            segment_id=s.segment_id,
            item_id="L1-1",
            list="list1",
            detector="Atomic topic",
            char_start=0,
            char_end=6,
        )
        for s in doc.segments
    )
    assert substantive_hits(hits, doc) == hits



def test_numeric_or_control_heading_retains_its_own_evidence(atom_document):
    doc = atom_document(
        "Drones 12",
        "Drones were tested with cameras along the perimeter "
        "during the recent flight trial by the operational unit.",
    )
    hits = tuple(
        Hit(
            segment_id=s.segment_id,
            item_id="L2-04",
            list="list2",
            detector="Atomic topic",
            char_start=0,
            char_end=6,
        )
        for s in doc.segments
    )
    assert substantive_hits(hits, doc) == hits
