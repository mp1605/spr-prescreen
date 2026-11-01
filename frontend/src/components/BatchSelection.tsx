import { Play, X } from "lucide-react";
import type { AIStatus } from "../api/ai";
import { uploadIssue, type SelectedUpload } from "../logic/uploads";
import { SCAN_MODE_LABELS, type ScanMode } from "../logic/scanModes";

export function BatchSelection({
  files,
  busy,
  reading,
  cancelling,
  scanMode,
  ai,
  aiLoading,
  defaultsLoading = false,
  remove,
  chooseMode,
  refreshAI,
  start,
  cancel,
}: {
  files: SelectedUpload[];
  busy: boolean;
  reading: boolean;
  cancelling: boolean;
  scanMode: ScanMode;
  ai: AIStatus | undefined;
  aiLoading: boolean;
  defaultsLoading?: boolean;
  remove: (id: number) => void;
  chooseMode: (value: ScanMode) => void;
  refreshAI: () => void;
  start: () => void;
  cancel: () => void;
}) {
  const eligible =
    !!ai?.available && ai.models.some((m) => m.name === ai.settings.model);
  const invalid = files.some((file) => uploadIssue(file));
  const useAI = scanMode !== "off";
  return (
    <div className="batch-selection">
      <div className="selection-ai">
        <div className="scan-mode-field">
          <label htmlFor="batch-scan-mode">Scan mode</label>
          <select
            id="batch-scan-mode"
            value={scanMode}
            disabled={busy || reading}
            onChange={(event) => chooseMode(event.target.value as ScanMode)}
          >
            {Object.entries(SCAN_MODE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <p>
          Rules and local semantic screening always run. Local LLM adds an
          optional review step.
        </p>
        {useAI && (
          <>
            <p role="status">
              {aiLoading
                ? "Checking local Ollama…"
                : eligible
                  ? `${ai?.settings.model} · ${ai?.settings.timeout_seconds} seconds maximum per paper, including queue wait.`
                  : "Local LLM is not ready. Start Ollama with the configured model, then refresh—or choose Python scanner."}
            </p>
            <button
              type="button"
              className="text-button"
              disabled={busy || aiLoading}
              onClick={refreshAI}
            >
              Refresh local LLM status
            </button>
            <p className="subtle">
              {scanMode === "selective"
                ? "Ollama reviews baseline-flagged passages and one neighboring segment on each side within the same section. With no candidates, the AI step is skipped. This is not a full-paper LLM review."
                : "Ollama reviews all extracted readable text. If the full input cannot fit, the AI step reports incomplete."}
            </p>
          </>
        )}
      </div>
      <div className="selection-heading">
        <h3>Selected files ({files.length}/100)</h3>
        <span className="subtle">
          {busy
            ? "Starting your batch. File selection is locked until the upload completes."
            : "Nothing is uploaded or scanned until you select Start scan."}
        </span>
      </div>
      <ul className="selected-files" aria-label="Selected files">
        {files.map((value) => (
          <li key={value.id}>
            <div className="selected-file-name">
              <strong>{value.path}</strong>
              <span className={uploadIssue(value) ? "error" : "subtle"}>
                {uploadIssue(value) ??
                  `${(value.file.size / 1024 ** 2).toFixed(2)} MiB · Ready`}
              </span>
            </div>
            <button
              type="button"
              className="outline-button"
              disabled={busy || reading}
              aria-label={`Remove ${value.path}`}
              onClick={() => remove(value.id)}
            >
              <X size={15} /> Remove
            </button>
          </li>
        ))}
      </ul>
      {invalid && (
        <p className="error" role="alert">
          Remove the unsupported or excluded files before starting.
        </p>
      )}
      <div className="selection-actions">
        <button
          type="button"
          className="primary-button"
          onClick={start}
          disabled={
            busy ||
            reading ||
            !files.length ||
            invalid ||
            defaultsLoading ||
            (useAI && (!eligible || aiLoading))
          }
        >
          <Play size={15} />
          {busy
            ? "Starting batch…"
            : defaultsLoading
              ? "Checking scan settings…"
              : `Start scan (${files.length})`}
        </button>
        <button
          type="button"
          className="outline-button"
          onClick={cancel}
          disabled={cancelling}
        >
          <X size={15} />
          {cancelling ? "Cancellation requested…" : "Cancel"}
        </button>
      </div>
    </div>
  );
}
