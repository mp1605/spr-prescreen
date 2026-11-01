"""Read-only cross-batch item navigation; use existing revision-checked decision writes."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from backend.core.batch import BatchService
from backend.core.item_review import ItemReview
from backend.core.item_review_models import ItemIndex, ItemPage
from backend.core.policy import OFFICIAL_IDS
from backend.core.review_store import ReviewStore

RunID = Annotated[str, Field(pattern=r"^web-[a-f0-9]{32}$")]
Runs = Annotated[list[RunID] | None, Query(max_length=100)]


def items_router(service: BatchService, reviews: ReviewStore) -> APIRouter:
    router = APIRouter(prefix="/api/review/items")
    items = ItemReview(service.store, reviews)

    @router.get("", response_model=ItemIndex)
    def index(run_id: Runs = None) -> ItemIndex:
        return items.snapshot(service.rules, tuple(run_id) if run_id is not None else None)[0]

    @router.get("/{item_id}", response_model=ItemPage)
    def page(
        item_id: str,
        run_id: Runs = None,
        review_status: Literal["all", "pending", "reviewed"] = "all",
        color: Literal["all", "red", "yellow"] = "all",
        search: Annotated[str, Query(max_length=200)] = "",
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        if_snapshot: Annotated[str | None, Query(pattern=r"^[a-f0-9]{64}$")] = None,
    ) -> ItemPage:
        if item_id not in OFFICIAL_IDS:
            raise HTTPException(404, "Official item not found")
        return items.page(
            service.rules,
            item_id,
            run_ids=tuple(run_id) if run_id is not None else None,
            review_status=review_status,
            color=color,
            search=search,
            offset=offset,
            limit=limit,
            if_snapshot=if_snapshot,
        )

    return router
