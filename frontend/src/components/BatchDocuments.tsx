import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get } from "../api/client";
import { send } from "../api/workflow";

interface FolderStatus {
  path: string;
  exists: boolean;
  counts: Record<string, number>;
  errors: string[];
}

export function BatchDocuments({
  runId,
  active,
}: {
  runId: string;
  active: boolean;
}) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const path = `/api/batches/${runId}/folders`;
  const query = useQuery({
    queryKey: ["batch-folders", runId],
    queryFn: () => get<FolderStatus>(path),
    refetchInterval: active ? 2000 : false,
  });
  async function update() {
    setBusy(true);
    setError("");
    try {
      client.setQueryData(
        ["batch-folders", runId],
        await send<FolderStatus>(path),
      );
      await client.invalidateQueries({ queryKey: ["decisions"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Folder update failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="audit-details batch-documents">
      <summary>
        Batch document folders
        {query.data
          ? ` · ${query.data.counts.Approved} approved · ${query.data.counts.Flagged} flagged · ${query.data.counts["Pending Review"]} pending`
          : ""}
      </summary>
      {query.data && (
        <>
          <p>
            Green papers await your approval. Red and yellow papers stay
            together in Flagged. Copies keep the original PDF or Word format.
          </p>
          <p className="folder-path">
            <code>{query.data.path}</code>
          </p>
          <p>In Finder, press ⌘⇧G and paste this path.</p>
          <button
            className="outline-button"
            disabled={busy}
            onClick={() => void update()}
          >
            {busy
              ? "Updating folders…"
              : query.data.exists
                ? "Update batch folders"
                : "Create batch folders"}
          </button>
          {!!query.data.errors.length && (
            <div role="alert" className="notice error">
              {query.data.errors.map((value, i) => (
                <p key={i}>{value}</p>
              ))}
            </div>
          )}
        </>
      )}
      {(query.error || error) && (
        <p role="alert" className="notice error">
          {error || query.error?.message}
          <button className="text-button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </p>
      )}
    </details>
  );
}
