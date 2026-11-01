export interface Health {
  status: "ok";
  milestone: "M12";
  color_stage: "specificity-v1";
  evaluation_harness_available: true;
  sponsor_evaluation_state: "deferred" | "complete" | "error";
  ingestion_available: true;
  screening_available: true;
  screening_stage: "rules_semantic";
  rules_version: string;
  list1_count: number;
  list2_count: number;
  detector_count: number;
  disclaimer: string;
  release_decision: "NOT_MADE_BY_TOOL";
}
export interface RuleItem {
  id: string;
  text: string;
  source_pages: number[];
  category: string | null;
  examples: string | null;
  detectors: {
    kind: "regex" | "keywords";
    name: string;
    item_id: string;
    pattern: string | null;
    terms: string[];
    case_sensitive: boolean;
    guard: "none" | "classification_marking" | "acknowledgment" | "byline";
    context_pattern: string | null;
    context_scope: "unit" | "nearby" | "document";
  }[];
}
export interface Registry {
  policy_version: string;
  source_document: string;
  source_sha256: string;
  list_execution_order: ["list1", "list2"];
  short_circuit: false;
  color_rules: Record<string, string>;
  list1: RuleItem[];
  list2: RuleItem[];
}
export interface SystemStatus {
  bind: string;
  python: string;
  models: { ready: boolean; files: number; bytes: number; message: string };
  ai_enabled: boolean;
  rules_detectors: number;
  semantic_enabled: true;
  semantic_state: string;
  semantic_model: string;
  semantic_reference_source: "official_rules_only";
  semantic_reference_count: 39;
  semantic_reference_digest: string;
  semantic_mid_threshold: number;
  semantic_high_threshold: number;
  feedback_usage: "excluded_during_blind_build";
  evaluation_mode: "blind";
  sponsor_material_access: boolean;
  evaluation_harness_available: true;
  sponsor_evaluation_state: "deferred" | "complete" | "error";
  semantic_calibrated: false;
  airlock_installed: boolean;
  specificity_enabled: true;
  specificity_version: "specificity-v1";
  specificity_policy_digest: string;
  optional_entity_model_state: string;
}
export async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { signal: AbortSignal.timeout(10000) });
  if (!response.ok)
    throw new Error(`Local service returned HTTP ${response.status}`);
  return (await response.json()) as T;
}
