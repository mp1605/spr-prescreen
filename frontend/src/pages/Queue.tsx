import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Layers, ArrowDownWideNarrow, X, RefreshCw } from "lucide-react";
import { get, type Registry } from "../api/client";
import { loadBatches, send, terminal, type Batch } from "../api/workflow";
import { UploadBatch } from "../components/UploadBatch";
import { ExportDownloads } from "../components/ExportDownloads";
import { BatchSummary } from "../components/BatchSummary";
import { BatchDocuments } from "../components/BatchDocuments";
import { QueueFilters } from "../components/QueueFilters";
import { QueueTable } from "../components/QueueTable";
import { QueryState } from "../components/QueryState";
import { useBatchEvents } from "../hooks/useBatchEvents";
import { filterQueue } from "../logic/queue";
import "../workflow.css";

export function Queue() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [order, setOrder] = useState("greens"),
    [search, setSearch] = useState("");
  const [color, setColor] = useState("all"),
    [list, setList] = useState("all");
  const [item, setItem] = useState("all"),
    [review, setReview] = useState("all");
  const [error, setError] = useState(""),
    [working, setWorking] = useState(false);
  const query = useQuery({
    queryKey: ["batches"],
    queryFn: loadBatches,
    refetchInterval: (state) =>
      state.state.data?.some((batch) =>
        batch.entries.some((entry) => !terminal(entry)),
      )
        ? 2000
        : false,
  });
  const rules = useQuery({
    queryKey: ["rules"],
    queryFn: () => get<Registry>("/api/rules"),
  });
  const batches = query.data ?? [];
  const batch =
    batches.find((candidate) => candidate.run_id === params.get("batch")) ??
    batches[0];
  const active = batch?.entries.some((entry) => !terminal(entry)) ?? false;
  const connection = useBatchEvents(batch?.run_id, active);
  const refresh = useCallback(
    () => void client.invalidateQueries({ queryKey: ["batches"] }),
    [client],
  );
  const act = useCallback(
    async (path: string) => {
      setWorking(true);
      setError("");
      try {
        await send(path);
        refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Action failed");
      } finally {
        setWorking(false);
      }
    },
    [refresh],
  );
  function created(value: Batch) {
    setParams({ batch: value.run_id });
    refresh();
  }
  const entries = batch?.entries ?? [];
  const filtered = filterQueue(entries, batch?.reviews ?? {}, {
    search,
    color,
    list,
    item,
    review,
  });
  return (
    <>
      <UploadBatch onCreated={created} />
      {query.isPending ? (
        <QueryState error={null} retry={refresh} />
      ) : (
        query.error && (
          <div className="notice error" role="alert">
            Could not refresh the queue.{" "}
            <button className="text-button" onClick={refresh}>
              Try again
            </button>
          </div>
        )
      )}
      {batch ? (
        <>
          <BatchSummary
            batch={batch}
            batches={batches}
            connection={connection}
            select={(id) => setParams({ batch: id })}
          />
          <ExportDownloads base={`/api/batches/${batch.run_id}`} />
          <BatchDocuments
            key={batch.run_id}
            runId={batch.run_id}
            active={active}
          />
          <section className="queue-panel">
            <div className="queue-heading">
              <div>
                <h2>
                  Review queue{" "}
                  <span className="count-pill">{entries.length}</span>
                </h2>
                <p>
                  {entries.filter(terminal).length}/{entries.length} processed ·{" "}
                  {entries.filter((entry) => entry.phase === "rejected").length}{" "}
                  rejected ·{" "}
                  {
                    entries.filter((entry) => entry.phase === "cancelled")
                      .length
                  }{" "}
                  cancelled
                </p>
              </div>
              <div className="queue-actions">
                {!active && (
                  <button
                    className="outline-button"
                    disabled={working}
                    onClick={() => {
                      setWorking(true);
                      setError("");
                      void send<Batch>(`/api/batches/${batch.run_id}/rescan`)
                        .then(created)
                        .catch((err: unknown) =>
                          setError(
                            err instanceof Error
                              ? err.message
                              : "Rescan failed",
                          ),
                        )
                        .finally(() => setWorking(false));
                    }}
                  >
                    <RefreshCw size={15} />
                    Rescan with current rules
                  </button>
                )}
                {active && (
                  <button
                    disabled={working}
                    className="outline-button"
                    onClick={() =>
                      void act(`/api/batches/${batch.run_id}/cancel`)
                    }
                  >
                    <X size={15} />
                    Cancel remaining
                  </button>
                )}
                <label className="sort-control">
                  <ArrowDownWideNarrow size={16} />
                  <select
                    aria-label="Queue order"
                    value={order}
                    onChange={(event) => setOrder(event.target.value)}
                  >
                    <option value="greens">Greens first</option>
                    <option value="red">Red first</option>
                    <option value="flags">Most flags first</option>
                  </select>
                </label>
              </div>
            </div>
            <QueueFilters
              search={search}
              color={color}
              list={list}
              item={item}
              review={review}
              rules={rules.data}
              setSearch={setSearch}
              setColor={setColor}
              setList={setList}
              setItem={setItem}
              setReview={setReview}
            />
            {error && (
              <p className="notice error" role="alert">
                {error}
              </p>
            )}
            <QueueTable
              batch={batch}
              entries={filtered}
              order={order}
              retry={(id) => {
                if (!working)
                  void act(`/api/batches/${batch.run_id}/papers/${id}/retry`);
              }}
            />
          </section>
        </>
      ) : (
        !query.isPending &&
        !query.error && (
          <section className="queue-empty">
            <div className="empty-art">
              <Layers size={32} />
            </div>
            <h2>Your review queue starts here.</h2>
            <p>
              Choose a batch above. Every result will link to its source
              evidence.
            </p>
            <span className="subtle">
              Green means “No flags found.” A reviewer still decides.
            </span>
          </section>
        )
      )}
    </>
  );
}
