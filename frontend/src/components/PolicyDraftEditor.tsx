import { useState } from "react";
import { adminRequest, type Draft } from "../api/admin";
import { PolicyValidation } from "./PolicyValidation";
import { PolicyImpact } from "./PolicyImpact";

export function PolicyDraftEditor({
  draft,
  update,
  published,
}: {
  draft: Draft;
  update: (draft: Draft) => void;
  published: () => void;
}) {
  const [text, setText] = useState(draft.yaml_text),
    [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState(""),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const dirty = text !== draft.yaml_text,
    running = draft.state === "previewing",
    done = draft.state === "published";
  const base = `/rules/drafts/${draft.draft_id}`;
  async function act(action: string) {
    setBusy(action);
    setError("");
    try {
      if (action === "save")
        update(
          await adminRequest<Draft>(base, "PUT", {
            revision: draft.revision,
            yaml_text: text,
          }),
        );
      else if (action === "validate")
        update(
          await adminRequest<Draft>(`${base}/validate`, "POST", {
            revision: draft.revision,
          }),
        );
      else if (action === "preview") {
        const body = new FormData();
        files.forEach((file) => body.append("files", file));
        const result = await adminRequest<{ draft: Draft }>(
          `${base}/preview?revision=${draft.revision}`,
          "POST",
          body,
        );
        update(result.draft);
      } else {
        await adminRequest(`${base}/publish`, "POST", {
          revision: draft.revision,
          preview_id: draft.preview_id,
          change_note: note,
        });
        published();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rule action failed.");
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="policy-draft" aria-label="Policy draft">
      <div className="admin-section-heading">
        <h3>
          {draft.restore_from
            ? `Restore ${draft.restore_from}`
            : "Indicator draft"}
        </h3>
        <span className="tag">
          {draft.state} · revision {draft.revision}
        </span>
      </div>
      <p>
        Based on {draft.base_version}. Official wording, numbering and color
        rules are protected. New version numbers are assigned on publication.
      </p>
      {done ? (
        <p role="status">
          Published as {draft.published_version}. Create a new draft for another
          change.
        </p>
      ) : (
        <>
          <label className="yaml-editor">
            Policy YAML
            <textarea
              spellCheck={false}
              value={text}
              disabled={!!busy || running}
              onChange={(event) => setText(event.target.value)}
              maxLength={524288}
              rows={18}
            />
          </label>
          <div className="admin-actions">
            <button
              className="outline-button"
              onClick={() => void act("save")}
              disabled={!dirty || !!busy || running}
            >
              Save draft
            </button>
            <button
              className="outline-button"
              onClick={() => void act("validate")}
              disabled={dirty || !!busy || running}
            >
              Validate saved draft
            </button>
            <span className="subtle">
              {dirty
                ? "Unsaved changes · save before validating"
                : "Saved draft"}
            </span>
          </div>
        </>
      )}
      <PolicyValidation report={draft.validation} />
      {!done && (
        <div className="preview-upload">
          <h3>Preview on permitted files</h3>
          <p>
            Select PDF/DOCX files explicitly. Do not use sponsor samples, tests,
            keys or expected results during this blind build. No folders or past
            batches are searched.
          </p>
          <label>
            Preview PDF/DOCX files
            <input
              type="file"
              multiple
              accept=".pdf,.docx"
              disabled={!!busy || running}
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []))
              }
            />
          </label>
          <small>{files.length} selected · up to 100 files, 25 MiB each</small>
          <button
            className="outline-button"
            onClick={() => void act("preview")}
            disabled={
              dirty ||
              !!busy ||
              running ||
              !draft.validation?.valid ||
              !files.length ||
              files.length > 100
            }
          >
            Start impact preview
          </button>
        </div>
      )}
      {draft.preview_id && <PolicyImpact id={draft.preview_id} />}
      {!done && (
        <div className="publish-panel">
          <h3>
            {draft.restore_from
              ? "Publish rollback"
              : "Publish validated indicators"}
          </h3>
          <p>
            A complete, eligible preview of this exact draft is required. New
            batches use the published version; existing results and reviews stay
            unchanged.
          </p>
          <label>
            Change note
            <textarea
              rows={2}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={2000}
              disabled={!!busy || running}
            />
          </label>
          <button
            className="primary-button"
            disabled={
              dirty ||
              !!busy ||
              draft.state !== "previewed" ||
              note.trim().length < 3
            }
            onClick={() => void act("publish")}
          >
            {draft.restore_from
              ? "Publish rollback as new version"
              : "Publish rules"}
          </button>
        </div>
      )}
      {busy && (
        <p role="status">
          {busy === "preview"
            ? "Uploading explicit preview inputs…"
            : "Saving rule workflow…"}
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
