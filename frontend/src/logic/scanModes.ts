import type { AISettings } from "../api/ai";

export type ScanMode = "off" | "selective" | "full";
export const SCAN_MODE_LABELS: Record<ScanMode, string> = {
  off: "Python scanner — no Ollama",
  selective: "Selective AI",
  full: "Full AI",
};
export function scanModeFor(settings?: AISettings | null): ScanMode {
  return !settings?.enabled
    ? "off"
    : settings.scope === "selective"
      ? "selective"
      : "full";
}
