import type { Validation } from "../api/admin";
export function PolicyValidation({ report }: { report: Validation | null }) {
  if (!report)
    return (
      <p className="subtle">
        Save and validate the draft before previewing impact.
      </p>
    );
  return (
    <section className="policy-validation" aria-label="Draft validation">
      <h3>
        {report.valid ? "Validation passed" : "Validation needs attention"}
      </h3>
      <p>
        {report.detector_count} indicators · {report.changes.length} changed
        fields
      </p>
      {!!report.errors.length && (
        <ul className="notice error" role="alert">
          {report.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
      {!report.changes.length && report.valid && (
        <p>No content changes from the active policy.</p>
      )}
      {report.changes.map((change, index) => (
        <details key={index} className="policy-change" open={change.protected}>
          <summary>
            {change.item_id ?? "Registry"} · {change.field}{" "}
            {change.protected
              ? "· Protected field changed"
              : "· Indicator edit"}
          </summary>
          <div className="policy-diff">
            <div>
              <strong>Active</strong>
              <pre>{change.before}</pre>
            </div>
            <div>
              <strong>Draft</strong>
              <pre>{change.after}</pre>
            </div>
          </div>
        </details>
      ))}
    </section>
  );
}
