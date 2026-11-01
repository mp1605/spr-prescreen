import type { Finding, ReviewState } from "../api/workflow";
export function ReviewAudit({
  state,
  flags,
}: {
  state: ReviewState;
  flags: Finding[];
}) {
  return (
    <details className="audit-details">
      <summary>Review audit trail · {state.events.length} events</summary>
      {!!state.feedback_examples?.length && (
        <p>
          {state.feedback_examples.length} active feedback examples retained
          with their source decisions. They are excluded from blind-build
          semantic matching. Undo withdraws the corresponding active example.
        </p>
      )}
      <ol>
        {state.events.map((event) => (
          <li key={event.event_id}>
            <strong>{event.action}</strong> · {event.reviewer} ·{" "}
            {new Date(event.utc).toLocaleString()}
            <span>
              {event.finding_id
                ? `Flag ${flags.findIndex((flag) => flag.finding_id === event.finding_id) + 1}`
                : "Source inspection"}
              {event.reason ? ` · ${event.reason}` : ""}
            </span>
          </li>
        ))}
      </ol>
      {!state.events.length && <p>No decisions recorded yet.</p>}
    </details>
  );
}
