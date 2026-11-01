import type { Finding, ReviewEvent } from "../api/workflow";
import type { RuleItem } from "../api/client";
import { StatusChip } from "./StatusChip";
import { SemanticEvidence } from "./SemanticEvidence";
import { AIEvidence } from "./AIEvidence";
import { ColorEvidence } from "./ColorEvidence";

export function FlagCard({
  flag,
  index,
  active,
  decision,
  items,
  select,
  accept,
  override,
  busy,
}: {
  flag: Finding;
  index: number;
  active: boolean;
  decision: ReviewEvent | undefined;
  items: Map<string, RuleItem>;
  select: () => void;
  accept: () => void;
  override: () => void;
  busy: boolean;
}) {
  return (
    <article
      className={`flag-card ${active ? "active" : ""}`}
      aria-label={`Flag ${index + 1}: ${flag.items.join(", ")}`}
    >
      <button className="flag-select" aria-pressed={active} onClick={select}>
        <span className="flag-number">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span>
          <strong>{flag.items.join(" · ")}</strong>
          <small>
            {flag.location.page
              ? `Page ${flag.location.page}`
              : `Paragraph ${flag.location.paragraph}`}
            {flag.location.heading ? ` · ${flag.location.heading}` : ""}
          </small>
        </span>
        <span className="evidence-link">View evidence ↗</span>
      </button>
      <StatusChip
        color={flag.color}
        label={flag.color === "red" ? "Flag identified" : "Potential flag"}
      />
      <blockquote>{flag.quote}</blockquote>
      <details>
        <summary>Official item wording ({flag.items.length})</summary>
        {flag.items.map((id) => (
          <p key={id}>
            <strong>{id}</strong>{" "}
            {items.get(id)?.text ??
              "Official rule unavailable. Open the Rules screen."}
          </p>
        ))}
      </details>
      <p className="flag-reason">{flag.reason}</p>
      <ColorEvidence assessment={flag.assessment ?? null} />
      {flag.why_unsure && (
        <p className="uncertainty">
          <strong>Why unsure</strong>
          {flag.why_unsure}
        </p>
      )}
      <div className="engine-badges">
        {flag.engines.map((engine) => (
          <span key={engine}>
            {engine === "rules"
              ? "Rules"
              : engine === "semantic"
                ? "Semantic"
                : "AI"}
          </span>
        ))}
        {flag.score !== null && <span>Cosine {flag.score.toFixed(3)}</span>}
      </div>
      <AIEvidence matches={flag.ai_matches ?? []} />
      <SemanticEvidence matches={flag.semantic_matches ?? []} />
      {flag.nearest_exemplar && (
        <p>Nearest exemplar: {flag.nearest_exemplar}</p>
      )}
      {decision && (
        <p className="decision-record">
          <strong>
            {decision.action === "accept" ? "Accepted" : "Overridden"}
          </strong>{" "}
          · {decision.reviewer}
          {decision.reason && <span>{decision.reason}</span>}
          {decision.feedback && (
            <span>
              {decision.feedback.polarity === "positive"
                ? "Positive"
                : "Negative"}{" "}
              feedback saved · excluded from blind-build matching
            </span>
          )}
        </p>
      )}
      <div className="flag-actions">
        <button
          disabled={busy}
          className={
            decision?.action === "accept" ? "outline-button" : "primary-button"
          }
          onClick={accept}
        >
          Accept flag <kbd>A</kbd>
        </button>
        <button disabled={busy} className="outline-button" onClick={override}>
          Override <kbd>O</kbd>
        </button>
      </div>
    </article>
  );
}
