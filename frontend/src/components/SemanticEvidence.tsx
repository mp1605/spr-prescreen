import type { SemanticMatch } from "../api/workflow";

export function SemanticEvidence({ matches }: { matches: SemanticMatch[] }) {
  if (!matches.length) return null;
  const nearest = matches[0];
  return (
    <section
      className="semantic-evidence"
      aria-label="Semantic policy evidence"
    >
      <div className="semantic-evidence-heading">
        <strong>Nearest official reference</strong>
        <span>
          {nearest.score.toFixed(3)} <small>cosine</small>
        </span>
      </div>
      <p>
        <strong>{nearest.item_id}</strong> {nearest.text}
      </p>
      <small>
        {nearest.band === "high" ? "High" : "Possible"} similarity · thresholds
        uncalibrated
      </small>
      {matches.length > 1 && (
        <details>
          <summary>
            {matches.length - 1} more matching reference
            {matches.length > 2 ? "s" : ""}
          </summary>
          {matches.slice(1).map((reference) => (
            <p key={reference.item_id}>
              <strong>
                {reference.item_id} · {reference.score.toFixed(3)}
              </strong>
              <br />
              {reference.text}
            </p>
          ))}
        </details>
      )}
      <p className="semantic-caution">
        Similarity is a retrieval signal, not a probability that this item
        applies.
      </p>
    </section>
  );
}
