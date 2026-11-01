"""Item-based navigation over completed browser results, never a rescan or source discovery."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from backend.core.batch_models import TERMINAL
from backend.core.item_review_models import ItemFinding, ItemIndex, ItemPage, ItemScope, ItemSummary
from backend.core.review_store import ReviewConflict, ReviewStore
from backend.core.rules_loader import RuleRegistry
from backend.core.run_store import RunStore


class ItemReview:
    def __init__(self, store: RunStore, reviews: ReviewStore) -> None:
        self.store, self.reviews = store, reviews

    def snapshot(
        self, registry: RuleRegistry, run_ids: tuple[str, ...] | None = None
    ) -> tuple[ItemIndex, dict[str, list[ItemFinding]]]:
        """One consistent in-process snapshot with at most one audit read per run."""
        with self.store.lock:
            batches = (
                tuple(self.store.read(run) for run in sorted(set(run_ids)))
                if run_ids is not None
                else self.store.list()
            )
            batches = tuple(sorted(batches, key=lambda b: (b.created, b.run_id), reverse=True))
            groups: dict[str, list[ItemFinding]] = {
                rule.id: [] for rule in (*registry.list1, *registry.list2)
            }
            digest = hashlib.sha256(registry.model_dump_json().encode())
            complete = unfinished = unavailable = incomplete = unique = 0
            for batch in batches:
                states = self.reviews.states(batch.run_id)
                digest.update(batch.model_dump_json().encode())
                digest.update(
                    json.dumps(
                        {key: value.revision for key, value in sorted(states.items())},
                        sort_keys=True,
                    ).encode()
                )
                for entry in sorted(
                    batch.entries, key=lambda e: (e.file_name.casefold(), e.entry_id)
                ):
                    if entry.phase != "done" or entry.result is None:
                        unfinished += entry.phase not in TERMINAL
                        unavailable += entry.phase in TERMINAL
                        continue
                    complete += 1
                    paper, state = entry.result, states[entry.entry_id]
                    incomplete += bool(paper.incomplete_reasons or paper.incomplete_pages)
                    unique += len(paper.findings)
                    for finding in paper.findings:
                        value = ItemFinding(
                            run_id=batch.run_id,
                            entry_id=entry.entry_id,
                            file_name=entry.file_name,
                            file_type=paper.file_type,
                            paper_color=paper.color,
                            rules_version=paper.rules_version,
                            incomplete_reasons=paper.incomplete_reasons,
                            incomplete_pages=paper.incomplete_pages,
                            review_revision=state.revision,
                            decision=state.decisions.get(finding.finding_id),
                            finding=finding,
                            review_url=f"/review/{batch.run_id}/{entry.entry_id}",
                            decisions_url=(
                                f"/api/batches/{batch.run_id}/papers/{entry.entry_id}/decisions"
                            ),
                        )
                        for item_id in finding.items:
                            groups[item_id].append(value)
            scope = ItemScope(
                run_ids=tuple(b.run_id for b in batches),
                snapshot=digest.hexdigest(),
                completed_papers=complete,
                unfinished_entries=unfinished,
                unavailable_entries=unavailable,
                incomplete_papers=incomplete,
                unique_findings=unique,
            )
            summaries = []
            for rule in (*registry.list1, *registry.list2):
                rows = groups[rule.id]
                summaries.append(
                    ItemSummary(
                        item_id=rule.id,
                        list="list1" if rule.id.startswith("L1-") else "list2",
                        text=rule.text,
                        source_pages=rule.source_pages,
                        findings=len(rows),
                        papers=len({(r.run_id, r.entry_id) for r in rows}),
                        red=sum(r.finding.color == "red" for r in rows),
                        yellow=sum(r.finding.color == "yellow" for r in rows),
                        pending=sum(r.decision is None for r in rows),
                        accepted=sum(
                            bool(r.decision and r.decision.action == "accept") for r in rows
                        ),
                        overridden=sum(
                            bool(r.decision and r.decision.action == "override") for r in rows
                        ),
                    )
                )
            return ItemIndex(scope=scope, items=tuple(summaries)), groups

    def page(
        self,
        registry: RuleRegistry,
        item_id: str,
        *,
        run_ids: tuple[str, ...] | None = None,
        review_status: Literal["all", "pending", "reviewed"] = "all",
        color: Literal["all", "red", "yellow"] = "all",
        search: str = "",
        offset: int = 0,
        limit: int = 25,
        if_snapshot: str | None = None,
    ) -> ItemPage:
        if not 0 <= offset or not 1 <= limit <= 100:
            raise ValueError("Invalid page bounds")
        index, groups = self.snapshot(registry, run_ids)
        if item_id not in groups:
            raise KeyError("Official item not found")
        if if_snapshot is not None and if_snapshot != index.scope.snapshot:
            raise ReviewConflict("Item review changed. Refresh the index and restart pagination.")
        rows = [
            row
            for row in groups[item_id]
            if (color == "all" or row.finding.color == color)
            and search.casefold() in row.file_name.casefold()
            and (
                review_status == "all"
                or (review_status == "pending" and row.decision is None)
                or (review_status == "reviewed" and row.decision is not None)
            )
        ]
        return ItemPage(
            scope=index.scope,
            item=next(item for item in index.items if item.item_id == item_id),
            total=len(rows),
            offset=offset,
            limit=limit,
            has_more=offset + limit < len(rows),
            entries=tuple(rows[offset : offset + limit]),
        )
