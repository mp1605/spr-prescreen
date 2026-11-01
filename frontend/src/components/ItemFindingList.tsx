import { ArrowLeft, ArrowRight } from "lucide-react";
import { rowIdentity, type ItemFinding, type ItemPage } from "../api/items";
import { StatusChip } from "./StatusChip";

export function ItemFindingList({
  page,
  selected,
  choose,
  move,
  loading,
}: {
  page: ItemPage;
  selected: ItemFinding | null;
  choose: (row: ItemFinding) => void;
  move: (offset: number) => void;
  loading: boolean;
}) {
  return (
    <section className="item-results" aria-labelledby="item-results-title">
      <div className="pane-heading">
        <h2 id="item-results-title">
          Matching findings <span className="count-pill">{page.total}</span>
        </h2>
        <span>J / K navigate</span>
      </div>
      {!page.entries.length ? (
        <div className="queue-empty">
          <h3>No findings match</h3>
          <p>
            Choose another item, batch or filter. This is a review view, not an
            evaluation result.
          </p>
        </div>
      ) : (
        <ol className="item-result-list">
          {page.entries.map((row) => (
            <li key={rowIdentity(row)}>
              <button
                className={`item-result ${selected && rowIdentity(selected) === rowIdentity(row) ? "active" : ""}`}
                aria-pressed={
                  !!selected && rowIdentity(selected) === rowIdentity(row)
                }
                onClick={() => choose(row)}
              >
                <strong>{row.file_name}</strong>
                <StatusChip
                  color={row.finding.color}
                  label={
                    row.finding.color === "red"
                      ? "Flag identified"
                      : "Potential flag"
                  }
                />
                <span className="item-result-quote">{row.finding.quote}</span>
                <small>
                  {row.finding.location.page
                    ? `Page ${row.finding.location.page}`
                    : `Paragraph ${row.finding.location.paragraph}`}{" "}
                  ·{" "}
                  {row.decision
                    ? `${row.decision.action === "accept" ? "Accepted" : "Overridden"} by ${row.decision.reviewer}`
                    : "Needs review"}
                </small>
                <small>
                  Batch {row.run_id.slice(-8)} · {row.rules_version}
                </small>
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="item-pagination">
        <button
          className="outline-button"
          disabled={!page.offset || loading}
          onClick={() => move(Math.max(0, page.offset - page.limit))}
        >
          <ArrowLeft size={15} />
          Previous page
        </button>
        <span role="status">
          {page.total
            ? `${page.offset + 1}–${Math.min(page.offset + page.entries.length, page.total)} of ${page.total}`
            : "0 findings"}
        </span>
        <button
          className="outline-button"
          disabled={!page.has_more || loading}
          onClick={() => move(page.offset + page.limit)}
        >
          Next page
          <ArrowRight size={15} />
        </button>
      </div>
    </section>
  );
}
