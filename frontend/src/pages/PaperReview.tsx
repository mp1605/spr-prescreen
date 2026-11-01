import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { get, type Registry } from "../api/client";
import {
  loadBatches,
  paperPath,
  type DocumentView,
  type Entry,
} from "../api/workflow";
import { QueryState } from "../components/QueryState";
import { ReviewWorkspace } from "../components/ReviewWorkspace";
import "../workflow.css";

export function PaperReview() {
  const { runId = "", entryId = "" } = useParams(),
    base = paperPath(runId, entryId);
  const query = useQuery({
    queryKey: ["paper", base],
    queryFn: async () => {
      const entry = await get<Entry>(base);
      const document =
        entry.phase === "done"
          ? await get<DocumentView>(`${base}/document`)
          : null;
      return { entry, document };
    },
  });
  const rules = useQuery({
    queryKey: ["rules"],
    queryFn: () => get<Registry>("/api/rules"),
  });
  const batches = useQuery({ queryKey: ["batches"], queryFn: loadBatches });
  if (!query.data || !rules.data || !batches.data)
    return (
      <QueryState
        error={query.error ?? rules.error ?? batches.error}
        retry={() => {
          void query.refetch();
          void rules.refetch();
          void batches.refetch();
        }}
      />
    );
  if (!query.data.document || !query.data.entry.result)
    return (
      <section className="panel">
        <h1>Paper is not ready for review</h1>
        <p>{query.data.entry.message}</p>
        <Link to={`/?batch=${runId}`} className="text-link">
          Return to the batch queue
        </Link>
      </section>
    );
  return (
    <ReviewWorkspace
      key={base}
      runId={runId}
      entry={query.data.entry}
      document={query.data.document}
      registry={rules.data}
      batches={batches.data}
    />
  );
}
