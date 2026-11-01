import { useState } from "react";
import {
  Download,
  FileJson,
  FileSpreadsheet,
  LoaderCircle,
} from "lucide-react";

interface Manifest {
  review_revision: number;
  warnings: string[];
}
async function download(path: string, fallback: string) {
  const response = await fetch(path, { signal: AbortSignal.timeout(90000) });
  if (!response.ok) {
    let message = `Download failed (HTTP ${response.status}).`;
    try {
      const data: unknown = await response.json();
      if (
        typeof data === "object" &&
        data &&
        "detail" in data &&
        typeof data.detail === "string"
      )
        message = data.detail;
    } catch {
      /* Keep HTTP status. */
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const name =
    response.headers
      .get("Content-Disposition")
      ?.match(/filename="([^"]+)"/)?.[1] ?? fallback;
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return response.headers.get("X-Review-Revision");
}
export function ExportDownloads({
  base,
  format,
  disabled = false,
}: {
  base: string;
  format?: "pdf" | "docx";
  disabled?: boolean;
}) {
  const [notes, setNotes] = useState(false);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const [message, setMessage] = useState(""),
    [warnings, setWarnings] = useState<string[]>([]);
  async function save(kind: string) {
    setBusy(kind);
    setError("");
    setMessage("");
    setWarnings([]);
    try {
      let manifest: Manifest | undefined;
      if (kind === "annotated") {
        const response = await fetch(
          `${base}/annotation-manifest?notes=${notes}`,
          {
            signal: AbortSignal.timeout(90000),
          },
        );
        const data: unknown = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data === "object" &&
            data &&
            "detail" in data &&
            typeof data.detail === "string"
              ? data.detail
              : "Annotated copy could not be prepared. Export the batch report instead.",
          );
        manifest = data as Manifest;
      }
      const path = format
        ? `${base}/${kind}?notes=${notes}`
        : `${base}/export/${kind}`;
      const revision = await download(
        path,
        kind === "annotated"
          ? `document-annotated.${format}`
          : `report.${kind === "annotation-manifest" ? "json" : kind}`,
      );
      setWarnings(manifest?.warnings ?? []);
      setMessage(
        kind === "annotated"
          ? `Highlighted copy downloaded · review revision ${revision ?? manifest?.review_revision}. Raw screening colors retained.`
          : kind === "annotation-manifest"
            ? "Copy details downloaded, including original and annotated SHA-256 hashes."
            : "Batch summary downloaded: one row per paper, with scanner results.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Download failed. Try again.",
      );
    } finally {
      setBusy("");
    }
  }
  const buttons = format
    ? [
        {
          key: "annotated",
          label: `Highlighted ${format.toUpperCase()}`,
          icon: Download,
        },
        {
          key: "annotation-manifest",
          label: "Copy details JSON",
          icon: FileJson,
        },
      ]
    : [
        { key: "csv", label: "Export CSV", icon: FileSpreadsheet },
        { key: "json", label: "Export JSON", icon: FileJson },
      ];
  return (
    <section
      className={`export-downloads${format ? " export-downloads-paper" : ""}`}
      aria-label={format ? "Annotated review copy" : "Batch reports"}
    >
      <div className="export-description">
        <strong>{format ? "Downloads" : "Export this batch"}</strong>
        {!format && (
          <span>One row per paper · scanner results · five columns</span>
        )}
      </div>
      {format && (
        <label className="export-notes">
          <input
            type="checkbox"
            checked={notes}
            disabled={disabled || !!busy}
            onChange={(event) => {
              setNotes(event.target.checked);
              setMessage("");
              setWarnings([]);
              setError("");
            }}
          />{" "}
          Include review notes
        </label>
      )}
      <div className="export-actions">
        {buttons.map(({ key, label, icon: Icon }) => (
          <button
            type="button"
            className="outline-button"
            key={key}
            disabled={disabled || !!busy}
            onClick={() => void save(key)}
          >
            {busy === key ? (
              <LoaderCircle size={16} className="export-spinner" />
            ) : (
              <Icon size={16} />
            )}
            {busy === key ? "Preparing…" : label}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="export-message">
          {message}
        </p>
      )}
      {!!warnings.length && (
        <details className="export-warnings" open>
          <summary>
            {warnings.length} annotation note{warnings.length === 1 ? "" : "s"}{" "}
            placed on the document summary
          </summary>
          <p>
            Other Word stories are highlighted in place; their notes name the
            source part and paragraph.
          </p>
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
