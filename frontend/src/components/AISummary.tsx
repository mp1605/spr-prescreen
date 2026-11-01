import type { Paper } from "../api/workflow";
const issues: Record<string, string> = {
  no_candidates:
    "No baseline candidates were found. Selective AI made no generation request; no full-paper LLM review was performed.",
  deadline_exceeded: "The total per-paper deadline was reached.",
  provider_or_response_error:
    "The local model was unavailable, changed, or returned an incomplete/invalid response.",
  invalid_proposal: "Some suggestions used an invalid schema or item ID.",
  unbound_or_ambiguous_quote:
    "Some quotes were absent, ambiguous, excluded, or could not be verified.",
  conflicting_suggestions: "The model gave conflicting specificity claims.",
  context_budget:
    "The full paper and policy would exceed the conservative context budget.",
  source_budget: "The source cannot fit a bounded complete AI request.",
  merge_refused: "An AI merge failed its add-only integrity checks.",
};
export function AISummary({ paper }: { paper: Paper }) {
  if (!paper.ai)
    return (
      <p className="ai-off-note">
        Optional local AI {paper.ai_state} for this scan ·{" "}
        {paper.ai_state === "off"
          ? "E1/E2 results retained."
          : "Legacy model details unavailable."}
      </p>
    );
  const ai = paper.ai;
  return (
    <details className="semantic-scope ai-scope">
      <summary>
        Local AI · {ai.state} · {ai.accepted} accepted / {ai.rejected} rejected
      </summary>
      <p>
        {ai.scope === "selective" ? "Selective AI" : "Full AI"} · Input
        selected: {ai.source_segments}/
        {ai.total_source_segments || ai.source_segments} segments.
        {typeof ai.generation_attempted === "boolean" &&
          (ai.generation_attempted
            ? " Generation requested."
            : " No generation request was made.")}
      </p>
      <p>
        {ai.model} · {ai.seconds.toFixed(2)} seconds including worker wait ·{" "}
        {ai.context_tokens.toLocaleString()} configured context token budget.
        Quotes and IDs were checked; model judgments remain uncalibrated.
      </p>
      {ai.issue_codes.length > 0 && (
        <ul>
          {ai.issue_codes.map((code) => (
            <li key={code}>{issues[code] ?? code}</li>
          ))}
        </ul>
      )}
      {ai.model_digest && (
        <p className="source-note">
          Ollama-reported local model digest <code>{ai.model_digest}</code>
        </p>
      )}
      <p>
        Original rules and semantic candidates cannot be removed or downgraded
        by AI. A reviewer decides applicability and release.
      </p>
    </details>
  );
}
