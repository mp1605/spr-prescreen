"""Verify transcribed words directly against the supplied official PDF, not any test corpus."""

import re

import pymupdf

from backend.core.rules_loader import load_rules


def clean(value):
    return " ".join(value.replace("\u200b", "").split())


def test_all_official_item_wording_matches_source_pdf(project_root):
    rules = load_rules(project_root)
    with pymupdf.open(project_root / "docs/official-lists.pdf") as document:
        assert len(document) == 4
        official_list1 = []
        for page in document[:2]:
            for table in page.find_tables().tables:
                for row in table.extract()[1:]:
                    official_list1.append(("L1-" + clean(row[0]), clean(row[2])))
        official_list2 = []
        for page in document[2:]:
            official_list2.extend(clean(p) for p in re.split("[●•]", page.get_text())[1:])
        assert [(r.id, r.text) for r in rules.list1] == official_list1
        assert [r.text for r in rules.list2] == official_list2
