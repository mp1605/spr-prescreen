import type { Batch, Entry } from "../api/workflow";
interface Filters {
  search: string;
  color: string;
  list: string;
  item: string;
  review: string;
}
export function filterQueue(
  entries: Entry[],
  reviews: Batch["reviews"],
  { search, color, list, item, review }: Filters,
) {
  return entries.filter((entry) => {
    const paper = entry.result,
      progress = reviews[entry.entry_id];
    return (
      entry.file_name.toLowerCase().includes(search.toLowerCase()) &&
      (color === "all" ||
        paper?.color === color ||
        (color === "incomplete" &&
          (!!paper?.incomplete_reasons.length || entry.phase === "failed"))) &&
      (list === "all" || paper?.findings.some((flag) => flag.list === list)) &&
      (item === "all" ||
        paper?.findings.some((flag) => flag.items.includes(item))) &&
      (review === "all" ||
        (review === "reviewed" ? progress?.complete : !progress?.complete))
    );
  });
}
