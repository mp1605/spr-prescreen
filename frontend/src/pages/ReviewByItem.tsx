import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { get, type Registry } from "../api/client";
import {
  itemGet,
  rowIdentity,
  type ItemIndex,
  type ItemPage,
} from "../api/items";
import { loadBatches } from "../api/workflow";
import {
  ItemReviewFilters,
  ItemPolicySummary,
} from "../components/ItemReviewFilters";
import { ItemFindingList } from "../components/ItemFindingList";
import { ItemEvidence } from "../components/ItemEvidence";
import { QueryState } from "../components/QueryState";
import { useReviewKeys } from "../hooks/useReviewKeys";
import { useItemNavigation } from "../hooks/useItemNavigation";
import "../workflow.css";

export function ReviewByItem() {
  const [params, setParams] = useSearchParams();
  const run = params.get("batch") ?? "",
    item = params.get("item") ?? "L1-1";
  const review = params.get("review") ?? "all",
    color = params.get("color") ?? "all",
    search = params.get("search") ?? "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const client = useQueryClient();
  const batches = useQuery({ queryKey: ["batches"], queryFn: loadBatches });
  const rules = useQuery({
    queryKey: ["rules"],
    queryFn: () => get<Registry>("/api/rules"),
  });
  const scope = new URLSearchParams();
  if (run) scope.set("run_id", run);
  const index = useQuery({
    queryKey: ["item-index", run],
    queryFn: () => itemGet<ItemIndex>(`/api/review/items?${scope}`),
    refetchOnWindowFocus: false,
  });
  const filters = new URLSearchParams(scope);
  filters.set("review_status", review);
  filters.set("color", color);
  filters.set("search", search);
  filters.set("offset", String(offset));
  filters.set("limit", "10");
  if (index.data) filters.set("if_snapshot", index.data.scope.snapshot);
  const page = useQuery({
    queryKey: [
      "item-page",
      run,
      item,
      review,
      color,
      search,
      offset,
      index.data?.scope.snapshot,
    ],
    enabled: !!index.data,
    retry: false,
    queryFn: () =>
      itemGet<ItemPage>(
        `/api/review/items/${encodeURIComponent(item)}?${filters}`,
      ),
    refetchOnWindowFocus: false,
  });
  function change(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    next.delete("offset");
    setParams(next);
    navigation.clear();
  }
  function move(value: number) {
    const next = new URLSearchParams(params);
    next.set("offset", String(value));
    setParams(next);
  }
  function refresh() {
    move(0);
    void client.invalidateQueries({ queryKey: ["item-index"] });
    void page.refetch();
  }
  const navigation = useItemNavigation(page.data, move);
  const selected = navigation.selected;
  useReviewKeys(
    {
      j: () => navigation.next(),
      k: () => navigation.next(-1),
      n: () => navigation.next(),
    },
    page.isFetching,
  );
  if (!index.data || !rules.data || !batches.data)
    return (
      <QueryState
        error={index.error ?? rules.error ?? batches.error}
        retry={() => {
          void index.refetch();
          void rules.refetch();
          void batches.refetch();
        }}
      />
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Review by item</h1>
        </div>
        <button
          className="outline-button"
          disabled={index.isFetching}
          onClick={refresh}
        >
          <RefreshCw size={16} />
          Refresh findings
        </button>
      </div>
      <ItemReviewFilters
        run={run}
        item={item}
        review={review}
        color={color}
        search={search}
        batches={batches.data}
        index={index.data}
        change={change}
      />
      <ItemPolicySummary index={index.data} item={item} />
      {page.error ? (
        <div className="notice error" role="alert">
          <h2>Findings could not be refreshed</h2>
          <p>{page.error.message}</p>
          <button onClick={refresh}>Refresh and restart pagination</button>
        </div>
      ) : !page.data ? (
        <QueryState error={null} retry={refresh} />
      ) : (
        <ItemFindingList
          page={page.data}
          selected={selected}
          choose={navigation.choose}
          move={move}
          loading={page.isFetching}
        />
      )}
      {selected ? (
        <ItemEvidence
          key={rowIdentity(selected)}
          row={selected}
          registry={rules.data}
          next={() => navigation.next()}
          canNext={navigation.canNext}
        />
      ) : (
        <p className="notice" role="status">
          Select a finding above to inspect its highlighted source and record a
          decision. J selects the first finding.
        </p>
      )}
    </>
  );
}
