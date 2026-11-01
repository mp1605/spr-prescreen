import type { Finding, ReviewEvent } from "./workflow";

export interface ItemScope {
  run_ids: string[];
  snapshot: string;
  completed_papers: number;
  unfinished_entries: number;
  unavailable_entries: number;
  incomplete_papers: number;
  unique_findings: number;
}
export interface ItemSummary {
  item_id: string;
  list: "list1" | "list2";
  text: string;
  source_pages: number[];
  findings: number;
  papers: number;
  red: number;
  yellow: number;
  pending: number;
  accepted: number;
  overridden: number;
}
export interface ItemIndex {
  scope: ItemScope;
  items: ItemSummary[];
  count_convention: string;
}
export interface ItemFinding {
  run_id: string;
  entry_id: string;
  file_name: string;
  file_type: "pdf" | "docx";
  paper_color: "red" | "yellow" | "green";
  rules_version: string;
  incomplete_reasons: string[];
  incomplete_pages: number[];
  review_revision: number;
  decision: ReviewEvent | null;
  finding: Finding;
  review_url: string;
  decisions_url: string;
}
export interface ItemPage {
  scope: ItemScope;
  item: ItemSummary;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  entries: ItemFinding[];
}
export const rowIdentity = (row: ItemFinding) =>
  `${row.run_id}/${row.entry_id}/${row.finding.finding_id}`;

export async function itemGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { signal: AbortSignal.timeout(20000) });
  if (!response.ok) {
    const data = (await response.json()) as { detail?: string };
    throw new Error(
      data.detail ?? `Item review failed (HTTP ${response.status})`,
    );
  }
  return (await response.json()) as T;
}
