import { useEffect, useRef, useState } from "react";
import { rowIdentity, type ItemFinding, type ItemPage } from "../api/items";

export function useItemNavigation(
  page: ItemPage | undefined,
  move: (offset: number) => void,
) {
  const [selected, setSelected] = useState<ItemFinding | null>(null);
  const pending = useRef<{ offset: number; last: boolean } | null>(null);
  useEffect(() => {
    if (!page || !pending.current || pending.current.offset !== page.offset)
      return;
    const target = pending.current.last ? page.entries.at(-1) : page.entries[0];
    pending.current = null;
    setSelected(target ?? null);
  }, [page]);
  const rows = page?.entries ?? [];
  const current = selected
    ? rows.findIndex((row) => rowIdentity(row) === rowIdentity(selected))
    : -1;
  function next(delta = 1) {
    if (!page || !rows.length) return;
    const index = current + delta;
    if (index >= 0 && index < rows.length) setSelected(rows[index]);
    else if (index >= rows.length && page.has_more) {
      pending.current = { offset: page.offset + page.limit, last: false };
      move(pending.current.offset);
    } else if (index < 0 && page.offset) {
      pending.current = {
        offset: Math.max(0, page.offset - page.limit),
        last: true,
      };
      move(pending.current.offset);
    }
  }
  function clear() {
    pending.current = null;
    setSelected(null);
  }
  return {
    selected,
    choose: setSelected,
    clear,
    next,
    canNext:
      !!page && !!rows.length && (current < rows.length - 1 || page.has_more),
  };
}
