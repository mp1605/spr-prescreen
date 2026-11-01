import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adminRequest, type Draft, type History } from "../api/admin";
import { PolicyDraftEditor } from "./PolicyDraftEditor";
import { PolicyHistory } from "./PolicyHistory";

export function AdminWorkspace() {
  const client = useQueryClient();
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [id, setId] = useState(
      () => sessionStorage.getItem("spr-policy-draft") ?? "",
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const history = useQuery({
    queryKey: ["policy-history"],
    queryFn: () => adminRequest<History>("/rules/history"),
  });
  const drafts = useQuery({
    queryKey: ["policy-drafts"],
    queryFn: () => adminRequest<Draft[]>("/rules/drafts"),
  });
  const selected = useQuery({
    queryKey: ["policy-draft", id],
    enabled: !!id,
    queryFn: () => adminRequest<Draft>(`/rules/drafts/${id}`),
    refetchOnWindowFocus: false,
    refetchInterval: (query) =>
      query.state.data?.state === "previewing" ? 1000 : false,
  });
  function choose(value: string) {
    setId(value);
    sessionStorage.setItem("spr-policy-draft", value);
  }
  function update(value: Draft) {
    client.setQueryData(["policy-draft", value.draft_id], value);
    choose(value.draft_id);
    void drafts.refetch();
  }
  async function create(restore_from?: string) {
    setBusy(true);
    setError("");
    try {
      update(
        await adminRequest<Draft>("/rules/drafts", "POST", { restore_from }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create draft.");
    } finally {
      setBusy(false);
    }
  }
  function published() {
    void selected.refetch();
    void drafts.refetch();
    void history.refetch();
    void client.invalidateQueries({ queryKey: ["rules"] });
    void client.invalidateQueries({ queryKey: ["health"] });
  }
  return (
    <div className="admin-workspace">
      <div className="admin-actions">
        <button
          className="primary-button"
          disabled={busy}
          onClick={() => void create()}
        >
          New indicator draft
        </button>
        <label>
          Saved draft
          <select value={id} onChange={(event) => choose(event.target.value)}>
            <option value="">Select a saved draft</option>
            {drafts.data?.map((draft) => (
              <option key={draft.draft_id} value={draft.draft_id}>
                {draft.draft_id.slice(0, 8)} · {draft.state} ·{" "}
                {draft.base_version}
              </option>
            ))}
          </select>
        </label>
        {id && (
          <button
            className="outline-button"
            onClick={() =>
              void selected
                .refetch()
                .then(() => setEditorEpoch((value) => value + 1))
            }
          >
            Reload saved draft
          </button>
        )}
      </div>
      <p className="subtle">
        Draft → Validate → Preview → Publish. Reloading replaces unsaved editor
        text.
      </p>
      {(error || selected.error || history.error || drafts.error) && (
        <p className="notice error" role="alert">
          {error ||
            "Could not refresh the admin workspace. Sign in again or retry the action."}
        </p>
      )}
      {selected.data && (
        <PolicyDraftEditor
          key={`${selected.data.draft_id}:${selected.data.revision}:${editorEpoch}`}
          draft={selected.data}
          update={update}
          published={published}
        />
      )}
      {history.data && (
        <PolicyHistory
          history={history.data}
          restore={(file) => void create(file)}
          busy={busy}
        />
      )}
    </div>
  );
}
