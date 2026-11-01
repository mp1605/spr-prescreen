import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Upload, FolderOpen, Files } from "lucide-react";
import { get } from "../api/client";
import type { AIStatus } from "../api/ai";
import { send, type Batch } from "../api/workflow";
import {
  candidates,
  droppedFiles,
  uploadIssue,
  type UploadFile,
  type SelectedUpload,
} from "../logic/uploads";
import { BatchSelection } from "./BatchSelection";
import {
  SCAN_MODE_LABELS,
  scanModeFor,
  type ScanMode,
} from "../logic/scanModes";

export function UploadBatch({
  onCreated,
}: {
  onCreated: (batch: Batch) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const nextId = useRef(0),
    epoch = useRef(0),
    cancelRequested = useRef(false);
  const [selected, setSelected] = useState<SelectedUpload[]>([]);
  const [busy, setBusy] = useState(false),
    [reading, setReading] = useState(false);
  const [cancelling, setCancelling] = useState(false),
    [modeChoice, setModeChoice] = useState<ScanMode | null>(null);
  const [drag, setDrag] = useState(false),
    [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const ai = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => get<AIStatus>("/api/ai"),
    retry: false,
    staleTime: 5000,
  });
  const scanMode = modeChoice ?? scanModeFor(ai.data?.settings);
  const useAI = scanMode !== "off";
  const defaultsLoading = modeChoice === null && ai.isFetching;
  function resetInputs() {
    if (input.current) input.current.value = "";
    if (folder.current) folder.current.value = "";
  }
  function add(files: UploadFile[]) {
    if (busy || !files.length) return;
    setError("");
    if (selected.length + files.length > 100) {
      setError(
        "Choose at most 100 files. The additional selection was not added; remove files and try again.",
      );
      resetInputs();
      return;
    }
    const incoming = files.map((value) => ({ ...value, id: nextId.current++ }));
    setSelected((previous) => [...previous, ...incoming]);
    setMessage("Review your selection, then choose Start scan.");
    resetInputs();
  }
  function cancel() {
    if (busy) {
      cancelRequested.current = true;
      setCancelling(true);
      setMessage(
        "Cancellation requested. Waiting for the upload response so the batch can be cancelled safely.",
      );
      return;
    }
    epoch.current++;
    setReading(false);
    setSelected([]);
    setModeChoice(null);
    setError("");
    setMessage("Selection cancelled. No files were uploaded or scanned.");
    resetInputs();
  }
  async function start() {
    if (
      busy ||
      reading ||
      defaultsLoading ||
      !selected.length ||
      selected.some(uploadIssue)
    )
      return;
    const eligible =
      ai.data?.available &&
      ai.data.models.some((m) => m.name === ai.data.settings.model);
    if (useAI && (!eligible || ai.isFetching)) return;
    const files = [...selected];
    cancelRequested.current = false;
    setCancelling(false);
    setBusy(true);
    setError("");
    setMessage(`Uploading ${files.length} selected files…`);
    const form = new FormData();
    for (const { file, path } of files) form.append("files", file, path);
    try {
      const batch = await send<Batch>(`/api/batches?ai_mode=${scanMode}`, form);
      setSelected([]);
      resetInputs();
      if (cancelRequested.current) {
        try {
          await send(`/api/batches/${batch.run_id}/cancel`);
        } finally {
          onCreated(batch);
        }
        setMessage(
          "Batch cancellation requested. Any completed results remain in the queue.",
        );
      } else {
        onCreated(batch);
        setMessage(
          `${files.length} files received. Mode: ${SCAN_MODE_LABELS[scanModeFor(batch.ai_settings)]}.`,
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Batch could not be started. Try again.",
      );
      setMessage("");
    } finally {
      setBusy(false);
      setCancelling(false);
      cancelRequested.current = false;
    }
  }
  return (
    <section
      className={`upload-zone ${drag ? "dragging" : ""}`}
      aria-label="Batch upload"
      onDragOver={(event) => {
        event.preventDefault();
        if (!busy && !reading) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDrag(false);
        if (busy || reading) return;
        const generation = epoch.current;
        setReading(true);
        setError("");
        void droppedFiles(event.dataTransfer.items, event.dataTransfer.files)
          .then((files) => {
            if (generation === epoch.current) add(files);
          })
          .catch((err) => {
            if (generation === epoch.current) setError(String(err));
          })
          .finally(() => {
            if (generation === epoch.current) setReading(false);
          });
      }}
    >
      <div className="upload-symbol">
        <Upload size={24} />
      </div>
      <div className="upload-copy">
        <h2>Prepare your next batch.</h2>
        <p>
          Add files, review the selection, then start scanning. PDF & DOCX · 100
          files · 25 MiB each.
        </p>
        <span className="subtle">
          Processing stays on this machine. You can add or remove files before
          starting.
        </span>
      </div>
      <div className="upload-actions">
        <button
          type="button"
          className="primary-button"
          disabled={busy || reading}
          onClick={() => input.current?.click()}
        >
          <Files size={16} />
          {selected.length ? "Add files" : "Choose files"}
        </button>
        <button
          type="button"
          className="outline-button"
          disabled={busy || reading}
          onClick={() => folder.current?.click()}
        >
          <FolderOpen size={16} />
          Choose folder
        </button>
      </div>
      <input
        ref={input}
        className="sr-only"
        aria-label="Choose PDF or Word files"
        type="file"
        multiple
        disabled={busy || reading}
        onChange={(event) =>
          add(candidates(Array.from(event.target.files ?? [])))
        }
      />
      <input
        ref={folder}
        className="sr-only"
        aria-label="Choose folder of papers"
        type="file"
        multiple
        disabled={busy || reading}
        {...{ webkitdirectory: "", directory: "" }}
        onChange={(event) =>
          add(candidates(Array.from(event.target.files ?? [])))
        }
      />
      {
        <BatchSelection
          files={selected}
          busy={busy}
          reading={reading}
          cancelling={cancelling}
          scanMode={scanMode}
          ai={ai.data}
          aiLoading={ai.isFetching}
          chooseMode={setModeChoice}
          defaultsLoading={defaultsLoading}
          refreshAI={() => void ai.refetch()}
          start={() => void start()}
          cancel={cancel}
          remove={(id) => {
            setSelected((files) => files.filter((file) => file.id !== id));
            setError("");
          }}
        />
      }
      {reading && (
        <p className="upload-message" role="status">
          Reading the selected folder…
        </p>
      )}
      {message && (
        <p className="upload-message" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="upload-message error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
