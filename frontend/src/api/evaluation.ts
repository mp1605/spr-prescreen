export interface ScoreCase {
  case_id: string;
  expected_color: string;
  actual_color: string;
  trigger_count: number;
  matched_count: number;
  missed: {
    tag: string;
    quote: string;
    items: string[];
    color: string;
    reason: string;
  }[];
  false_alarms: { quote: string; items: string[]; color: string }[];
  decoy_hits: string[];
}
export interface EvaluationReport {
  kind: "format_contract" | "sponsor_evaluation";
  paper_count: number;
  trigger_count: number;
  matched_triggers: number;
  trigger_recall: number | null;
  list1_recall: number | null;
  list2_recall: number | null;
  item_accuracy: number | null;
  flag_color_accuracy: number | null;
  paper_color_accuracy: number;
  confusion: Record<string, Record<string, number>>;
  false_alarms: number;
  greens_wrongly_flagged: number;
  decoy_count: number;
  decoys_flagged: number;
  false_alarms_on_reference_papers: number;
  reference_paper_count?: number;
  incomplete_papers: number;
  seconds_per_paper_ai_off: number | null;
  seconds_per_paper_ai_on: number | null;
  rules_versions: string[];
  matching_policy: string;
  cost_assumption: string;
  weighted_cost: number;
  cases: ScoreCase[];
}
export interface ScorecardStatus {
  split: "dev" | "holdout";
  state: "deferred" | "complete";
  sponsor_material_access: boolean;
  sponsor_accuracy_measured: boolean;
  report: EvaluationReport | null;
  message: string;
  disclaimer: string;
}
export const rate = (value: number | null) =>
  value === null ? "Not defined" : `${(value * 100).toFixed(1)}%`;
