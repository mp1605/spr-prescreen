import { Search } from "lucide-react";
import type { Registry } from "../api/client";
interface Props {
  search: string;
  color: string;
  list: string;
  item: string;
  review: string;
  rules: Registry | undefined;
  setSearch: (v: string) => void;
  setColor: (v: string) => void;
  setList: (v: string) => void;
  setItem: (v: string) => void;
  setReview: (v: string) => void;
}
export function QueueFilters({
  search,
  color,
  list,
  item,
  review,
  rules,
  setSearch,
  setColor,
  setList,
  setItem,
  setReview,
}: Props) {
  return (
    <div className="queue-filters">
      <label className="search">
        <Search size={16} />
        <input
          aria-label="Search paper titles"
          placeholder="Search paper titles…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <select
        aria-label="Filter color"
        value={color}
        onChange={(event) => setColor(event.target.value)}
      >
        <option value="all">All colors</option>
        {["green", "yellow", "red", "incomplete"].map((value) => (
          <option key={value}>{value}</option>
        ))}
      </select>
      <select
        aria-label="Filter list"
        value={list}
        onChange={(event) => setList(event.target.value)}
      >
        <option value="all">Both lists</option>
        <option value="list1">List 1 flags</option>
        <option value="list2">List 2 flags</option>
      </select>
      <select
        aria-label="Filter item"
        value={item}
        onChange={(event) => setItem(event.target.value)}
      >
        <option value="all">All items</option>
        {[...(rules?.list1 ?? []), ...(rules?.list2 ?? [])].map((rule) => (
          <option key={rule.id} value={rule.id}>
            {rule.id}
          </option>
        ))}
      </select>
      <select
        aria-label="Filter review status"
        value={review}
        onChange={(event) => setReview(event.target.value)}
      >
        <option value="all">All reviews</option>
        <option value="pending">Needs review</option>
        <option value="reviewed">Reviewed</option>
      </select>
    </div>
  );
}
