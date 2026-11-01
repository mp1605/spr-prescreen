import { type Batch } from "../api/workflow";
import { SCAN_MODE_LABELS, scanModeFor } from "../logic/scanModes";
export function BatchSummary({
  batch,
  batches,
  connection,
  select,
}: {
  batch: Batch;
  batches: Batch[];
  connection: string;
  select: (id: string) => void;
}) {
  const entries = batch.entries;
  const count = (color: string) =>
    entries.filter((entry) => entry.result?.color === color).length;
  const incomplete = entries.filter(
    (entry) =>
      entry.result?.incomplete_reasons.length || entry.phase === "failed",
  ).length;
  const reviewed = Object.values(batch.reviews).filter(
    (state) => state.complete,
  ).length;
  return (
    <>
      {" "}
      <div className="batch-heading">
        <label>
          Batch{" "}
          <select
            aria-label="Select batch"
            value={batch.run_id}
            onChange={(event) => select(event.target.value)}
          >
            {batches.map((value) => (
              <option key={value.run_id} value={value.run_id}>
                {new Date(value.created).toLocaleString()} ·{" "}
                {value.entries.length} files · {value.run_id.slice(-6)}
              </option>
            ))}
          </select>
        </label>
        <span className="subtle">
          Mode: {SCAN_MODE_LABELS[scanModeFor(batch.ai_settings)]}
        </span>
        <span className="subtle" role="status">
          {connection}
        </span>
      </div>
      <div className="queue-stats">
        {[
          ["Green", count("green"), "No flags found"],
          ["Yellow", count("yellow"), "Potential / incomplete"],
          ["Red", count("red"), "Flag identified"],
          ["Incomplete", incomplete, "Source needs inspection"],
          ["Reviewed", reviewed, "Human review recorded"],
        ].map(([label, value, detail]) => (
          <article key={label} className={String(label).toLowerCase()}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{detail}</small>
          </article>
        ))}
      </div>
    </>
  );
}
