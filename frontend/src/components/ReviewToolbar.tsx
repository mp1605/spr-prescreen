import { ScanDetails } from "./ScanDetails";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Undo2 } from "lucide-react";
import { StatusChip } from "./StatusChip";
import type { Entry, ReviewState } from "../api/workflow";

export function ReviewToolbar({
  runId,
  entry,
  state,
  reviewer,
  setReviewer,
  undo,
  canUndo,
  busy,
  next,
  inspect,
}: {
  runId: string;
  entry: Entry;
  state: ReviewState;
  reviewer: string;
  setReviewer: (value: string) => void;
  undo: () => void;
  canUndo: boolean;
  busy: boolean;
  next: string;
  inspect: () => void;
}) {
  const paper = entry.result!;
  return (
    <>
      <Link className="back-link" to={`/?batch=${runId}`}>
        <ArrowLeft size={15} />
        Back to queue
      </Link>
      <div className="review-title">
        <div>
          <h1>{entry.file_name}</h1>
          <div className="review-meta">
            <StatusChip color={paper.color} label={paper.label} />
            <span>
              {paper.file_type.toUpperCase()} · {entry.seconds.toFixed(2)}s ·
              {paper.screening_stage === "rules_semantic"
                ? "Rules + Semantic"
                : "Rules only"}
              {" · AI "}
              {paper.ai_state}
            </span>
          </div>
        </div>
        <Link className="outline-button" to={next}>
          Next paper <kbd>N</kbd>
          <ArrowRight size={15} />
        </Link>
      </div>
      <ScanDetails paper={paper} />
      <div className="review-toolbar">
        <div>
          <strong>
            Reviewed {Object.keys(state.decisions).length}/
            {paper.flag_count.total}
          </strong>
          <progress
            max={Math.max(1, paper.flag_count.total)}
            value={Object.keys(state.decisions).length}
            aria-label="Flags reviewed"
          />
          <small>
            Accept or override a flag; the screening result stays unchanged.
          </small>
        </div>
        <label className="reviewer-input">
          Reviewer name
          <input
            value={reviewer}
            maxLength={100}
            placeholder="Your display name"
            onChange={(event) => setReviewer(event.target.value)}
          />
        </label>
        <button
          className="outline-button"
          onClick={undo}
          disabled={!canUndo || busy}
        >
          <Undo2 size={15} />
          Undo <kbd>U</kbd>
        </button>
        <button
          className="outline-button"
          disabled={busy || state.inspected || !reviewer.trim()}
          onClick={inspect}
        >
          {state.inspected
            ? "Source inspection recorded"
            : "Mark source inspected"}
        </button>
      </div>
      {!reviewer.trim() && (
        <p className="review-hint">
          Enter a reviewer name to record decisions in the local audit trail.
        </p>
      )}
      {!!paper.incomplete_reasons.length && (
        <div className="notice incomplete-notice">
          <strong>Incomplete source · manual inspection required</strong>
          <ul>
            {paper.incomplete_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p>
            Reviewing the extracted flags does not resolve unreadable or
            unsupported content.
          </p>
        </div>
      )}
    </>
  );
}
