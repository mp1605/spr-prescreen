export interface AISettings {
  enabled: boolean;
  scope?: "full" | "selective";
  model: string;
  model_digest: string | null;
  endpoint: "http://127.0.0.1:11434";
  timeout_seconds: number;
  context_tokens: number;
  max_output_tokens: number;
}
export interface AIStatus {
  settings: AISettings;
  revision: string;
  available: boolean;
  models: { name: string; digest: string; bytes: number }[];
  message: string;
}
export interface AIEvidence {
  item_id: string;
  quote: string;
  model_quote: string;
  char_start: number;
  char_end: number;
  match: "exact" | "normalized" | "fuzzy";
  similarity: number;
  clear_or_possible: "clear" | "possible";
  reason: string;
}
export interface AIInfo {
  version: "spr-ai-v1";
  provider: "ollama";
  model: string;
  model_digest: string | null;
  configured_model_digest: string | null;
  configuration_digest: string;
  pipeline_digest: string;
  prompt_digest: string | null;
  state: "ran" | "timeout" | "error" | "skipped";
  scope?: "full" | "selective";
  total_source_segments?: number;
  source_segment_ids?: string[];
  generation_attempted?: boolean | null;
  seconds: number;
  accepted: number;
  rejected: number;
  issue_codes: string[];
  context_tokens: number;
  timeout_seconds: number;
  max_output_tokens: number;
  source_segments: number;
  prompt_bytes: number;
}
