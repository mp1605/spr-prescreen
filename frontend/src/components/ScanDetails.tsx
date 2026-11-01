import { AISummary } from "./AISummary";
import type { Paper } from "../api/workflow";

export function ScanDetails({ paper }: { paper: Paper }) {
  return (
    <details className="scan-details">
      <summary>Scan details</summary>
      <div className="scan-details-body">
        {paper.semantic && (
          <details className="semantic-scope">
            <summary>
              Semantic pass{" "}
              {paper.semantic.state === "complete" ? "complete" : "incomplete"}{" "}
              · 39 official references · uncalibrated
            </summary>
            <p>
              Each source passage is compared with the official policy wording.
              Possible similarity starts at{" "}
              {paper.semantic.mid_threshold.toFixed(2)}; high similarity starts
              at {paper.semantic.high_threshold.toFixed(2)}. These scores are
              retrieval signals, not probabilities. List 1 candidates retain red
              severity.
              {paper.fusion
                ? " List 2 colors use the source-bound evidence shown for each item."
                : " This earlier scan retained preliminary yellow for List 2."}{" "}
              The semantic engine uses official policy references; saved
              reviewer feedback and sponsor answer keys are not retrieved during
              screening.
            </p>
          </details>
        )}
        {paper.fusion && (
          <details className="semantic-scope">
            <summary>
              Color assessment{" "}
              {paper.fusion.state === "complete" ? "complete" : "incomplete"} ·
              source-bound specificity
            </summary>
            <p>
              Overlapping passages are merged within each list. Each item
              retains its own specific/possible assessment, with the worst color
              setting the passage priority. Generic topics and
              judgment-dependent matches stay yellow. Assessment date:{" "}
              {paper.fusion.as_of_utc_date} UTC. Optional named-entity
              assistance: {paper.fusion.ner_state.replaceAll("_", " ")}.
            </p>
          </details>
        )}
        <AISummary paper={paper} />
        <div className="keyboard-strip">
          <span>
            <kbd>J</kbd>/<kbd>K</kbd> next / previous flag
          </span>
          <span>
            <kbd>A</kbd> accept
          </span>
          <span>
            <kbd>O</kbd> override
          </span>
          <span>
            <kbd>N</kbd> next paper
          </span>
          <span>
            <kbd>U</kbd> undo
          </span>
        </div>
      </div>
    </details>
  );
}
