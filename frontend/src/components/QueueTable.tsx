import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { type Batch, type Entry } from "../api/workflow";
import { queueColumns } from "./queueColumns";

export function QueueTable({
  batch,
  entries,
  order,
  retry,
}: {
  batch: Batch;
  entries: Entry[];
  order: string;
  retry: (id: string) => void;
}) {
  const columns = useMemo(() => queueColumns(batch, retry), [batch, retry]);
  const table = useReactTable({
    data: entries,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    state: {
      sorting: [
        { id: order === "flags" ? "flags" : "color", desc: order !== "greens" },
        { id: "paper", desc: false },
      ],
    },
  });
  return (
    <div className="table-scroll">
      <table className="queue-table">
        <caption className="sr-only">
          Screening queue,{" "}
          {order === "greens"
            ? "greens first"
            : order === "flags"
              ? "most flags first"
              : "red first"}
        </caption>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id} scope="col">
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.original.entry_id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!entries.length && (
        <div className="queue-empty">
          <h3>No papers match these filters.</h3>
          <p>Adjust the filters to bring papers back into view.</p>
        </div>
      )}
    </div>
  );
}
