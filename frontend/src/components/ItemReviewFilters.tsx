import { ListFilter } from "lucide-react";
import type { Batch } from "../api/workflow";
import type { ItemIndex } from "../api/items";

export function ItemReviewFilters({
  run,
  item,
  review,
  color,
  search,
  batches,
  index,
  change,
}: {
  run: string;
  item: string;
  review: string;
  color: string;
  search: string;
  batches: Batch[];
  index: ItemIndex;
  change: (key: string, value: string) => void;
}) {
  return (
    <section className="panel item-filters" aria-label="Item review filters">
      <label>
        Batch scope
        <select
          aria-label="Batch scope"
          value={run}
          onChange={(e) => change("batch", e.target.value)}
        >
          <option value="">All batches</option>
          {batches.map((b) => (
            <option key={b.run_id} value={b.run_id}>
              {new Date(b.created).toLocaleString()} · {b.entries.length} files
              · {b.run_id.slice(-6)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Official item
        <select
          aria-label="Official item"
          value={item}
          onChange={(e) => change("item", e.target.value)}
        >
          {index.items.map((i) => (
            <option key={i.item_id} value={i.item_id}>
              {i.item_id} · {i.findings} findings · {i.pending} pending
            </option>
          ))}
        </select>
      </label>
      <label>
        Review status
        <select
          aria-label="Review status"
          value={review}
          onChange={(e) => change("review", e.target.value)}
        >
          <option value="all">All findings</option>
          <option value="pending">Needs review</option>
          <option value="reviewed">Reviewed</option>
        </select>
      </label>
      <label>
        Screening priority
        <select
          aria-label="Screening priority"
          value={color}
          onChange={(e) => change("color", e.target.value)}
        >
          <option value="all">Red and yellow</option>
          <option value="red">Red findings</option>
          <option value="yellow">Yellow findings</option>
        </select>
      </label>
      <label>
        Search filenames
        <input
          aria-label="Search filenames"
          value={search}
          maxLength={200}
          placeholder="Filename contains…"
          onChange={(e) => change("search", e.target.value)}
        />
      </label>
    </section>
  );
}

export function ItemPolicySummary({
  index,
  item,
}: {
  index: ItemIndex;
  item: string;
}) {
  const current = index.items.find((value) => value.item_id === item);
  if (!current) return null;
  return (
    <section className="panel item-policy">
      <div className="eyebrow">
        <ListFilter size={15} />
        {current.item_id} · Guide p. {current.source_pages.join(", ")}
      </div>
      <h2>Official item wording</h2>
      <p>{current.text}</p>
      <div className="item-counts">
        <span>
          <strong>{current.findings}</strong> findings
        </span>
        <span>
          <strong>{current.papers}</strong> uploads
        </span>
        <span>
          <strong>{current.pending}</strong> pending
        </span>
        <span>
          <strong>{current.accepted}</strong> accepted
        </span>
        <span>
          <strong>{current.overridden}</strong> overridden
        </span>
      </div>
      <details>
        <summary>How these counts work</summary>
        <p>{index.count_convention}</p>
        <p>
          {index.scope.unfinished_entries} entries still processing ·{" "}
          {index.scope.unavailable_entries} unavailable ·{" "}
          {index.scope.incomplete_papers} incomplete sources.
        </p>
      </details>
    </section>
  );
}
