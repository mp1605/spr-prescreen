import type { AIEvidence as Evidence } from "../api/ai";
export function AIEvidence({ matches }: { matches: Evidence[] }) {
  if (!matches.length) return null;
  return (
    <details className="ai-evidence">
      <summary>
        Local AI evidence · {matches.length} verified suggestion
        {matches.length === 1 ? "" : "s"}
      </summary>
      <p>
        Quotes are source-checked. Item applicability and the model's reasoning
        still require human review.
      </p>
      {matches.map((match, index) => (
        <div className="ai-suggestion" key={index}>
          <strong>
            {match.item_id} · model suggests {match.clear_or_possible}
          </strong>
          <blockquote>{match.quote}</blockquote>
          <small>
            {match.match} source match · {match.similarity.toFixed(1)}{" "}
            similarity · offsets {match.char_start}–{match.char_end}
          </small>
          <p>{match.reason}</p>
          {match.quote !== match.model_quote && (
            <details>
              <summary>Model wording differed</summary>
              <blockquote>{match.model_quote}</blockquote>
              <p>
                The highlighted evidence above uses the original source wording.
              </p>
            </details>
          )}
        </div>
      ))}
    </details>
  );
}
