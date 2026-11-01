import { Circle, Diamond, Triangle } from "lucide-react";
import type { Color } from "../api/workflow";

export function StatusChip({ color, label }: { color: Color; label: string }) {
  const Icon =
    color === "red" ? Triangle : color === "yellow" ? Diamond : Circle;
  return (
    <span className={`status-chip ${color}`}>
      <Icon size={14} aria-hidden="true" />
      {color.toUpperCase()} · {label}
    </span>
  );
}
