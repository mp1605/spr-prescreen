import type { AIEvidence, AIInfo, AISettings } from "./ai";
import { get } from "./client";

export type Color = "green" | "yellow" | "red";
export interface SpecificityFeature {
  kind: string;
  text: string;
  char_start: number;
  char_end: number;
  source: "regex" | "local_ner";
}
export interface ColorAssessment {
  version: "specificity-v1";
  state: "complete" | "error";
  items: {
    item_id: string;
    disposition: "clear" | "possible";
    reason: string;
    evidence: SpecificityFeature[];
    rule_anchor: SpecificityFeature | null;
    ai_evidence: AIEvidence | null;
  }[];
}
export interface FusionInfo {
  version: "source-span-fusion-v1";
  specificity_version: "specificity-v1";
  policy_digest: string;
  as_of_utc_date: string;
  ner_state: "not_used" | "ready" | "unavailable";
  ner_model_digest: string | null;
  state: "complete" | "error";
}
export interface SemanticMatch {
  item_id: string;
  text: string;
  score: number;
  band: "high" | "possible";
  source: "official_rule";
}
export interface SemanticInfo {
  version: "official-bge-v1";
  model: "BAAI/bge-small-en-v1.5";
  dimensions: 384;
  reference_source: "official_rules_only";
  reference_count: 39;
  reference_digest: string;
  model_digest: string | null;
  high_threshold: number;
  mid_threshold: number;
  calibrated: false;
  feedback_usage: "excluded_during_blind_build";
  state: "complete" | "error";
  segments: number;
  chunks: number;
  cache_state: "not_used" | "hit" | "miss" | "unavailable";
  seconds: number;
}
export interface FeedbackExample {
  finding_id: string;
  paper_id: string;
  rules_version: string;
  items: string[];
  quote: string;
  polarity: "positive" | "negative";
  source: "reviewer_decision";
  usage: "excluded_during_blind_build";
}
export interface Finding {
  finding_id: string;
  paper_id: string;
  list: "list1" | "list2";
  items: string[];
  color: "red" | "yellow";
  quote: string;
  location: {
    page: number | null;
    paragraph: number | null;
    heading: string | null;
    char_start: number;
    char_end: number;
    bbox: number[][] | null;
  };
  reason: string;
  why_unsure: string | null;
  engines: ("rules" | "semantic" | "ai")[];
  score: number | null;
  nearest_exemplar: string | null;
  semantic_matches: SemanticMatch[];
  assessment: ColorAssessment | null;
  ai_matches: AIEvidence[];
}
export interface Paper {
  paper_id: string;
  file_name: string;
  file_type: "pdf" | "docx";
  screening_stage: "rules_only" | "rules_semantic";
  semantic: SemanticInfo | null;
  fusion: FusionInfo | null;
  color: Color;
  label: string;
  flag_count: { total: number; red: number; yellow: number };
  lists_checked: string[];
  trace: string[];
  incomplete_pages: number[];
  incomplete_reasons: string[];
  ai_state: "off" | "ran" | "timeout" | "error" | "skipped";
  ai: AIInfo | null;
  rules_version: string;
  seconds: number;
  release_decision: "NOT_MADE_BY_TOOL";
  findings: Finding[];
}
export interface Entry {
  entry_id: string;
  file_name: string;
  phase:
    | "queued"
    | "parsing"
    | "list1"
    | "list2"
    | "ai"
    | "done"
    | "failed"
    | "rejected"
    | "cancelled";
  message: string;
  attempt: number;
  seconds: number;
  result: Paper | null;
}
export interface Batch {
  run_id: string;
  created: string;
  ai_settings: AISettings | null;
  rules_version: string;
  revision: number;
  entries: Entry[];
  reviews: Record<
    string,
    { reviewed: number; complete: boolean; approved?: boolean }
  >;
}
export interface ReviewEvent {
  event_id: string;
  entry_id: string;
  finding_id: string | null;
  action: "accept" | "override" | "inspect" | "approve" | "undo";
  reason: string | null;
  reviewer: string;
  utc: string;
  target_event: string | null;
  feedback: Pick<FeedbackExample, "finding_id" | "polarity" | "usage"> | null;
}
export interface ReviewState {
  revision: number;
  decisions: Record<string, ReviewEvent>;
  inspected: boolean;
  events: ReviewEvent[];
  feedback_examples: FeedbackExample[];
  approved?: boolean;
  approval_event?: ReviewEvent | null;
  storage_file?: string | null;
  storage_error?: string | null;
}
export interface SourceUnit {
  unit_id: number;
  part: string;
  page: number | null;
  paragraph: number | null;
  heading: string | null;
  text: string;
  width: number | null;
  height: number | null;
  excluded: { char_start: number; char_end: number; reason: string }[];
}
export interface DocumentView {
  units: SourceUnit[];
  page_rotations?: Record<number, number>;
}
export const terminal = (entry: Entry) =>
  ["done", "failed", "rejected", "cancelled"].includes(entry.phase);
export const priority = (entry: Entry) =>
  entry.result ? { green: 0, yellow: 1, red: 2 }[entry.result.color] : 3;
export const paperPath = (run: string, entry: string) =>
  `/api/batches/${run}/papers/${entry}`;

export async function send<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers:
      body instanceof FormData ? {} : { "Content-Type": "application/json" },
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `Local service returned HTTP ${response.status}`;
    try {
      const data: unknown = await response.json();
      if (
        typeof data === "object" &&
        data &&
        "detail" in data &&
        typeof data.detail === "string"
      )
        detail = data.detail;
    } catch {
      /* HTTP status remains useful. */
    }
    throw new Error(detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
export const loadBatches = () => get<Batch[]>("/api/batches");
