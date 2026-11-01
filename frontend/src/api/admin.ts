import type { Paper } from "./workflow";
export interface Session {
  configured: boolean;
  authenticated: boolean;
  role: "admin" | "reviewer";
  expires_utc: string | null;
}
export interface Validation {
  valid: boolean;
  errors: string[];
  detector_count: number;
  yaml_sha256: string;
  changes: {
    item_id: string | null;
    field: string;
    before: string;
    after: string;
    protected: boolean;
  }[];
}
export interface Draft {
  draft_id: string;
  revision: number;
  base_version: string;
  base_sha256: string;
  yaml_text: string;
  validation: Validation | null;
  preview_id: string | null;
  restore_from: string | null;
  state: "draft" | "validated" | "previewing" | "previewed" | "published";
  published_version: string | null;
}
export interface Preview {
  preview_id: string;
  state: "queued" | "running" | "complete" | "failed" | "interrupted";
  eligible: boolean;
  message: string;
  sponsor_metrics: "NOT_MEASURED";
  entries: {
    file_name: string;
    sha256: string;
    before: Paper | null;
    after: Paper | null;
    changed: boolean;
    message: string;
  }[];
}
export interface History {
  active: {
    version: string;
    sha256: string;
    published_by: string;
    utc: string;
    change_note: string;
  };
  versions: {
    file: string;
    version: string;
    sha256: string;
    restorable: boolean;
  }[];
  audit: {
    operation: string;
    version: string;
    actor: string;
    utc: string;
    note: string;
  }[];
}
export async function adminRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/admin${path}`, {
    method,
    headers:
      body instanceof FormData
        ? {}
        : body === undefined
          ? {}
          : { "Content-Type": "application/json" },
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    let message = `Admin request failed (HTTP ${response.status}).`;
    try {
      const data: unknown = await response.json();
      if (
        typeof data === "object" &&
        data &&
        "detail" in data &&
        typeof data.detail === "string"
      )
        message = data.detail;
    } catch {
      /* Keep HTTP status. */
    }
    throw new Error(message);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
