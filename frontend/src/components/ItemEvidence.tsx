import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get, type Registry } from "../api/client";
import type { ItemFinding } from "../api/items";
import {
  paperPath,
  type DocumentView,
  type Entry,
  type ReviewState,
} from "../api/workflow";
import { useReviewActions } from "../hooks/useReviewActions";
import { useReviewKeys } from "../hooks/useReviewKeys";
import { DocumentViewer } from "./DocumentViewer";
import { FlagCard } from "./FlagCard";
import { OverrideDialog } from "./OverrideDialog";
import { QueryState } from "./QueryState";

export function ItemEvidence({
  row,
  registry,
  next,
  canNext,
}: {
  row: ItemFinding;
  registry: Registry;
  next: () => void;
  canNext: boolean;
}) {
  const base = paperPath(row.run_id, row.entry_id);
  const source = useQuery({
    queryKey: ["paper", base],
    queryFn: async () => ({
      entry: await get<Entry>(base),
      document: await get<DocumentView>(`${base}/document`),
    }),
  });
  const decisions = useQuery({
    queryKey: ["decisions", base],
    queryFn: () => get<ReviewState>(row.decisions_url),
  });
  const [reviewer, setReviewer] = useState(
    () => localStorage.getItem("spr-reviewer") ?? "",
  );
  const [pulse, setPulse] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const panel = useRef<HTMLElement>(null);
  const ready = !!source.data && !!decisions.data;
  useEffect(() => {
    if (!ready) return;
    panel.current?.scrollIntoView({
      block: "start",
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    panel.current?.focus({ preventScroll: true });
  }, [ready]);
  const actions = useReviewActions(base, decisions.data, reviewer);
  const accept = () =>
    actions.save({ action: "accept", finding_id: row.finding.finding_id });
  function override() {
    if (reviewer.trim()) dialog.current?.showModal();
    else
      actions.save({ action: "override", finding_id: row.finding.finding_id });
  }
  useReviewKeys(
    { a: accept, o: override, u: actions.undo },
    actions.busy || !decisions.data || !source.data,
  );
  if (!source.data || !decisions.data)
    return (
      <QueryState
        error={source.error ?? decisions.error}
        retry={() => {
          void source.refetch();
          void decisions.refetch();
        }}
      />
    );
  const paper = source.data.entry.result;
  if (!paper)
    return (
      <p className="notice error" role="alert">
        This result is no longer ready. Refresh the item list.
      </p>
    );
  const flag = paper.findings.find(
    (f) => f.finding_id === row.finding.finding_id,
  );
  if (!flag)
    return (
      <p className="notice error" role="alert">
        The finding is unavailable in the current result. Refresh the item list.
      </p>
    );
  return (
    <section
      className="item-evidence"
      aria-labelledby="selected-finding-title"
      ref={panel}
      tabIndex={-1}
    >
      <div className="pane-heading">
        <div>
          <h2 id="selected-finding-title">{row.file_name}</h2>
          <small>Selected source evidence · {row.rules_version}</small>
        </div>
        <Link
          className="text-link"
          to={`${row.review_url}?finding=${encodeURIComponent(flag.finding_id)}`}
        >
          Full paper review ↗
        </Link>
      </div>
      <div className="item-review-controls">
        <label>
          Reviewer name
          <input
            maxLength={100}
            value={reviewer}
            placeholder="Your display name"
            onChange={(e) => {
              setReviewer(e.target.value);
              localStorage.setItem("spr-reviewer", e.target.value);
            }}
          />
        </label>
        <button
          className="outline-button"
          onClick={actions.undo}
          disabled={!actions.undoable || actions.busy}
        >
          Undo <kbd>U</kbd>
        </button>
        <button
          className="outline-button"
          onClick={next}
          disabled={actions.busy || !canNext}
        >
          {canNext ? (
            <>
              Next finding <kbd>N</kbd>
            </>
          ) : (
            "End of matching findings"
          )}
        </button>
      </div>
      {!reviewer.trim() && (
        <p className="review-hint">
          Enter your name to record a decision. Source evidence stays unchanged.
        </p>
      )}
      {(source.error || decisions.error) && (
        <p className="notice error" role="alert">
          Could not refresh the source or decisions.{" "}
          <button
            onClick={() => {
              void source.refetch();
              void decisions.refetch();
            }}
          >
            Retry
          </button>
        </p>
      )}
      {!!(paper.incomplete_reasons.length || paper.incomplete_pages.length) && (
        <div className="notice" role="status">
          <strong>Incomplete source requires manual inspection.</strong>
          <p>{paper.incomplete_reasons.join(" · ")}</p>
          <p>Use full paper review to record source inspection.</p>
        </div>
      )}
      <div className="item-evidence-grid">
        <div className="document-panel">
          <DocumentViewer
            document={source.data.document}
            findings={paper.findings}
            active={flag.finding_id}
            base={base}
            pulse={pulse}
          />
        </div>
        <div>
          <FlagCard
            flag={flag}
            index={0}
            active
            decision={decisions.data.decisions[flag.finding_id]}
            items={
              new Map(
                [...registry.list1, ...registry.list2].map((item) => [
                  item.id,
                  item,
                ]),
              )
            }
            select={() => setPulse((p) => p + 1)}
            accept={accept}
            override={override}
            busy={actions.busy || !reviewer.trim()}
          />
          <p
            className={
              actions.toast.startsWith("Not saved") ? "notice error" : "notice"
            }
            role="status"
            aria-live="polite"
          >
            {actions.busy
              ? "Saving decision…"
              : actions.toast ||
                "Review the source, then accept or override. A / O / U shortcuts are available."}
          </p>
        </div>
      </div>
      <OverrideDialog
        ref={dialog}
        save={(reason) =>
          actions.save({
            action: "override",
            finding_id: flag.finding_id,
            reason: reason.trim() || undefined,
          })
        }
      />
    </section>
  );
}
