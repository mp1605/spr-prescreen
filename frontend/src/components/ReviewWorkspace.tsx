import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get, type Registry } from "../api/client";
import {
  paperPath,
  priority,
  type Batch,
  type DocumentView,
  type Entry,
  type ReviewState,
} from "../api/workflow";
import { useReviewActions } from "../hooks/useReviewActions";
import { useReviewKeys } from "../hooks/useReviewKeys";
import { DocumentViewer } from "./DocumentViewer";
import { ReviewToolbar } from "./ReviewToolbar";
import { FlagList } from "./FlagList";
import { ReviewAudit } from "./ReviewAudit";
import { OverrideDialog } from "./OverrideDialog";
import { ExportDownloads } from "./ExportDownloads";
import { QueryState } from "./QueryState";

export function ReviewWorkspace({
  runId,
  entry,
  document,
  registry,
  batches,
}: {
  runId: string;
  entry: Entry;
  document: DocumentView;
  registry: Registry;
  batches: Batch[];
}) {
  const base = paperPath(runId, entry.entry_id),
    paper = entry.result!;
  const query = useQuery({
    queryKey: ["decisions", base],
    queryFn: () => get<ReviewState>(`${base}/decisions`),
    refetchOnWindowFocus: true,
  });
  const [reviewer, setName] = useState(
    () => localStorage.getItem("spr-reviewer") ?? "",
  );
  const [index, setIndex] = useState(0),
    [pulse, setPulse] = useState(0);
  const [params] = useSearchParams();
  const requested = params.get("finding");
  const overrideDialog = useRef<HTMLDialogElement>(null),
    flagsPane = useRef<HTMLDivElement>(null);
  const actions = useReviewActions(base, query.data, reviewer),
    navigate = useNavigate();
  const items = new Map(
    [...registry.list1, ...registry.list2].map((item) => [item.id, item]),
  );
  const flags = useMemo(
    () => [...paper.findings].sort((a, b) => a.list.localeCompare(b.list)),
    [paper.findings],
  );
  useEffect(() => {
    const target = flags.findIndex((flag) => flag.finding_id === requested);
    if (target >= 0) {
      setIndex(target);
      setPulse((value) => value + 1);
    }
  }, [requested, flags]);
  const selected = flags[index];
  const ordered = [
    ...(batches.find((batch) => batch.run_id === runId)?.entries ?? []),
  ]
    .filter((value) => value.phase === "done")
    .sort(
      (a, b) =>
        priority(a) - priority(b) || a.file_name.localeCompare(b.file_name),
    );
  const following =
    ordered[
      ordered.findIndex((value) => value.entry_id === entry.entry_id) + 1
    ];
  const next = following
    ? `/review/${runId}/${following.entry_id}`
    : `/?batch=${runId}`;
  function select(value: number) {
    if (value < 0 || value >= flags.length) return;
    setIndex(value);
    setPulse((count) => count + 1);
    const pane = flagsPane.current,
      card = pane?.querySelectorAll(".flag-card")[value];
    if (pane && card) {
      const box = card.getBoundingClientRect(),
        bounds = pane.getBoundingClientRect();
      const delta =
        box.top < bounds.top
          ? box.top - bounds.top - 38
          : box.bottom > bounds.bottom
            ? box.bottom - bounds.bottom
            : 0;
      pane.scrollTo({
        top: pane.scrollTop + delta,
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
    }
  }
  function accept() {
    if (selected)
      actions.save({ action: "accept", finding_id: selected.finding_id });
  }
  function override() {
    if (!reviewer.trim()) {
      actions.save({ action: "override", finding_id: selected?.finding_id });
      return;
    }
    if (selected) overrideDialog.current?.showModal();
  }
  useReviewKeys(
    {
      a: accept,
      o: override,
      j: () => select(Math.min(flags.length - 1, index + 1)),
      k: () => select(Math.max(0, index - 1)),
      n: () => void navigate(next),
      u: actions.undo,
    },
    actions.busy || !query.data,
  );
  if (!query.data)
    return (
      <QueryState error={query.error} retry={() => void query.refetch()} />
    );
  const state = query.data;
  return (
    <>
      <ReviewToolbar
        runId={runId}
        entry={entry}
        state={state}
        reviewer={reviewer}
        setReviewer={(value) => {
          setName(value);
          localStorage.setItem("spr-reviewer", value);
        }}
        undo={actions.undo}
        canUndo={!!actions.undoable}
        busy={actions.busy}
        next={next}
        inspect={() => actions.save({ action: "inspect" })}
        approve={() => actions.save({ action: "approve" })}
      />
      {query.error && (
        <div className="notice error" role="alert">
          Could not refresh decisions.{" "}
          <button className="text-button" onClick={() => void query.refetch()}>
            Refresh review state
          </button>
        </div>
      )}
      <ExportDownloads
        base={base}
        format={paper.file_type}
        disabled={actions.busy}
      />
      <div className="review-grid">
        <section className="document-panel">
          <div className="pane-heading">
            <h2>Source document</h2>
            <a className="text-link original-link" href={`${base}/original`}>
              Download original
            </a>
          </div>
          <DocumentViewer
            document={document}
            findings={flags}
            active={selected?.finding_id}
            base={base}
            pulse={pulse}
          />
        </section>
        <FlagList
          flags={flags}
          index={index}
          state={state}
          items={items}
          select={select}
          save={actions.save}
          reviewer={reviewer}
          busy={actions.busy}
          openOverride={() => overrideDialog.current?.showModal()}
          paneRef={flagsPane}
          paper={paper}
        />
      </div>
      <div
        className={`review-toast ${actions.toast.startsWith("Not saved") ? "error" : ""}`}
        role="status"
        aria-live="polite"
      >
        {actions.busy ? "Saving decision…" : actions.toast}
        {actions.toast && actions.undoable && !actions.busy && (
          <button className="text-button" onClick={actions.undo}>
            Undo <kbd>U</kbd>
          </button>
        )}
      </div>
      <ReviewAudit state={state} flags={flags} />
      <p className="source-note">
        {paper.rules_version} · {paper.paper_id} · Trace:{" "}
        {paper.trace.join(" → ")} · AI {paper.ai_state}
      </p>
      <OverrideDialog
        ref={overrideDialog}
        save={(reason) => {
          if (selected)
            actions.save({
              action: "override",
              finding_id: selected.finding_id,
              reason: reason.trim() || undefined,
            });
        }}
      />
    </>
  );
}
