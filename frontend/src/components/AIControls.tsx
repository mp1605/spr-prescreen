import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import { adminRequest, type Session } from "../api/admin";
import type { AIStatus } from "../api/ai";
import { AISettingsForm } from "./AISettingsForm";

export function AIControls() {
  const client = useQueryClient(),
    [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: ["ai-status"],
    queryFn: () => get<AIStatus>("/api/ai"),
  });
  const session = useQuery({
    queryKey: ["admin-session"],
    queryFn: () => adminRequest<Session>("/session"),
    refetchInterval: 60000,
  });
  return (
    <section className="panel ai-controls" aria-label="Optional local AI">
      <div className="admin-section-heading">
        <h2>Optional local AI</h2>
        <button
          className="outline-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {query.isFetching ? "Checking…" : "Refresh local models"}
        </button>
      </div>
      <p>
        E1 and E2 always run. Local AI can add source-verified suggestions and
        raise review priority; it cannot remove existing findings or determine
        release.
      </p>
      {!query.data ? (
        <p role="status">
          {query.error
            ? "Local model status could not be checked. Use Refresh local models to retry."
            : "Checking loopback service…"}
        </p>
      ) : (
        <>
          <p role="status">{query.data.message}</p>
          <dl className="status-list">
            <div>
              <dt>AI setting</dt>
              <dd>
                {query.data.settings.enabled
                  ? "Default on · batch selection can override"
                  : "Default off · batch selection can override"}
              </dd>
            </div>
            <div>
              <dt>Configured model</dt>
              <dd>{query.data.settings.model}</dd>
            </div>
            <div>
              <dt>Per-paper deadline</dt>
              <dd>
                {query.data.settings.timeout_seconds} seconds, including waiting
                for the single AI worker
              </dd>
            </div>
            <div>
              <dt>Eligible cached models</dt>
              <dd>
                {query.data.models.length
                  ? query.data.models.map((model) => model.name).join(", ")
                  : "None available"}
              </dd>
            </div>
          </dl>
          {session.data?.authenticated ? (
            <AISettingsForm
              key={query.data.revision}
              status={query.data}
              saved={(value) => {
                client.setQueryData(["ai-status"], value);
                void client.invalidateQueries({ queryKey: ["system"] });
                setMessage(
                  "AI settings saved. New batches use this configuration.",
                );
              }}
            />
          ) : (
            <p>
              <Link className="text-link" to="/rules#rule-management">
                Sign in on Official rules
              </Link>{" "}
              to configure AI. Reviewers can inspect its status.
            </p>
          )}
          {message && <p role="status">{message}</p>}
        </>
      )}
      <details>
        <summary>Local setup and limits</summary>
        <p>
          Use cached local GGUF weights. For first-time setup, start{" "}
          <code>./scripts/run_ollama.sh</code> from the project in another
          terminal, then refresh this inventory before enabling AI. Use{" "}
          <code>./scripts/run_ollama.sh --cpu</code> if Metal is unavailable.
          The project launcher starts cached Ollama on later launches when AI is
          enabled. This screen does not install or pull models.
        </p>
        <p>
          One generation request per paper. Over-budget input is refused rather
          than silently truncated. Missing models, timeouts and rejected
          suggestions keep E1/E2 findings and mark uncertainty. A verified quote
          does not establish that the AI item interpretation is correct.
        </p>
      </details>
    </section>
  );
}
