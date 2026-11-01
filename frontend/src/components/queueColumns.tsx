import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowUpRight, RotateCcw } from "lucide-react";
import { priority, type Batch, type Entry } from "../api/workflow";
import { StatusChip } from "./StatusChip";
export function queueColumns(
  batch: Batch,
  retry: (id: string) => void,
): ColumnDef<Entry>[] {
  return [
    {
      id: "paper",
      accessorKey: "file_name",
      header: "Paper",
      cell: ({ row }) => {
        const entry = row.original;
        return (
          <div className="paper-cell">
            {entry.phase === "done" ? (
              <Link to={`/review/${batch.run_id}/${entry.entry_id}`}>
                {entry.file_name}
                <ArrowUpRight size={14} />
              </Link>
            ) : (
              <strong>{entry.file_name}</strong>
            )}
            <small>
              {entry.result
                ? `List 1 → List 2 · ${entry.result.incomplete_reasons.length ? "Incomplete source" : "Both lists checked"}`
                : entry.message}
            </small>
          </div>
        );
      },
    },
    {
      id: "color",
      accessorFn: (entry) => (entry.result ? priority(entry) : undefined),
      sortUndefined: "last",
      header: "Screening result",
      cell: ({ row }) => {
        const entry = row.original;
        return entry.result ? (
          <StatusChip color={entry.result.color} label={entry.result.label} />
        ) : (
          <span className={`phase-chip ${entry.phase}`}>
            {entry.phase === "list1"
              ? "List 1"
              : entry.phase === "list2"
                ? "List 2"
                : entry.phase === "ai"
                  ? "Local AI"
                  : entry.phase}
          </span>
        );
      },
    },
    {
      id: "flags",
      accessorFn: (entry) => entry.result?.flag_count.total ?? -1,
      header: "Flags",
      cell: ({ row }) => {
        const count = row.original.result?.flag_count;
        return count ? (
          <div>
            <strong>{count.total}</strong>
            <small>
              {count.red} red · {count.yellow} yellow
            </small>
          </div>
        ) : (
          "—"
        );
      },
    },
    {
      id: "items",
      header: "Top items",
      cell: ({ row }) => {
        const items = [
          ...new Set(
            row.original.result?.findings.flatMap((flag) => flag.items) ?? [],
          ),
        ];
        return (
          <span className="item-ids" title={items.join(", ")}>
            {items.slice(0, 3).join(" · ") || "—"}
            {items.length > 3 ? ` +${items.length - 3}` : ""}
          </span>
        );
      },
    },
    {
      id: "review",
      header: "Review",
      cell: ({ row }) => {
        const entry = row.original,
          state = batch.reviews[entry.entry_id];
        if (["failed", "cancelled"].includes(entry.phase))
          return (
            <button
              className="text-button"
              onClick={() => retry(entry.entry_id)}
            >
              <RotateCcw size={13} />
              Retry
            </button>
          );
        if (!entry.result) return "—";
        return (
          <span>
            {state?.complete
              ? "Reviewed"
              : `${state?.reviewed ?? 0}/${entry.result.flag_count.total}`}
            <small>
              {entry.result.flag_count.total
                ? "flag decisions"
                : state?.complete
                  ? "Source inspected"
                  : "Inspect source"}
            </small>
          </span>
        );
      },
    },
    {
      id: "format",
      header: "Format",
      cell: ({ row }) => (
        <span className="format-label">
          {row.original.result?.file_type ??
            row.original.file_name.split(".").pop()?.toUpperCase()}
        </span>
      ),
    },
    {
      id: "time",
      header: "Time",
      cell: ({ row }) =>
        row.original.phase === "done"
          ? `${row.original.seconds.toFixed(2)}s`
          : "—",
    },
  ];
}
