import { useQuery } from "@tanstack/react-query";
import {
  HeaderRefresh,
  PageHeaderActions,
} from "../components/PageHeaderActions";
import { get, type SystemStatus } from "../api/client";
import { AIControls } from "../components/AIControls";
import { QueryState } from "../components/QueryState";

export function System() {
  const query = useQuery({
    queryKey: ["system"],
    queryFn: () => get<SystemStatus>("/api/system"),
  });
  if (!query.data)
    return (
      <QueryState error={query.error} retry={() => void query.refetch()} />
    );
  const status = query.data;
  return (
    <>
      <PageHeaderActions>
        <HeaderRefresh
          label="Refresh system status"
          busy={query.isFetching}
          refresh={() => void query.refetch()}
        />
      </PageHeaderActions>
      {query.error && (
        <p className="notice error" role="alert">
          Refresh failed. Showing the last received status.
        </p>
      )}
      <section className="panel">
        <h2>Runtime</h2>
        <dl className="status-list">
          <div>
            <dt>Rule indicators</dt>
            <dd>
              {status.rules_detectors} active · rules + semantic screening
            </dd>
          </div>
          <div>
            <dt>Configured service address</dt>
            <dd>{status.bind}</dd>
          </div>
          <div>
            <dt>Python</dt>
            <dd>{status.python}</dd>
          </div>
          <div>
            <dt>Color assessment</dt>
            <dd>{status.specificity_version} · source-bound evidence</dd>
          </div>
          <div>
            <dt>Optional entity assistance</dt>
            <dd>{status.optional_entity_model_state.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>Local AI</dt>
            <dd>{status.ai_enabled ? "Enabled" : "Off"}</dd>
          </div>
          <div>
            <dt>Scanner reference policy</dt>
            <dd>Official items only · no sponsor exemplars</dd>
          </div>
          <div>
            <dt>Evaluation harness</dt>
            <dd>
              {status.sponsor_evaluation_state === "complete"
                ? "Frozen evaluation complete · see scorecard"
                : status.sponsor_evaluation_state === "error"
                  ? "Stored report unavailable · see scorecard"
                  : "Prepared · no completed evaluation in this workspace"}
            </dd>
          </div>
        </dl>
      </section>
      <section className="panel">
        <h2>Model assets</h2>
        <p role="status">{status.models.message}</p>
        <dl className="status-list">
          <div>
            <dt>Files present</dt>
            <dd>{status.models.files}</dd>
          </div>
          <div>
            <dt>Size on disk</dt>
            <dd>{(status.models.bytes / 1024 / 1024).toFixed(1)} MB</dd>
          </div>
          <div>
            <dt>Semantic engine</dt>
            <dd>
              {status.semantic_model} ·{" "}
              {status.semantic_state.replaceAll("_", " ")}
            </dd>
          </div>
          <div>
            <dt>Active references</dt>
            <dd>
              {status.semantic_reference_count} official items · no sponsor
              exemplars
            </dd>
          </div>
          <div>
            <dt>Similarity bands</dt>
            <dd>
              Possible ≥ {status.semantic_mid_threshold.toFixed(2)} · High ≥{" "}
              {status.semantic_high_threshold.toFixed(2)}
            </dd>
          </div>
          <div>
            <dt>Reviewer feedback</dt>
            <dd>Stored with decisions · excluded from matching</dd>
          </div>
          <div>
            <dt>Semantic thresholds</dt>
            <dd>Uncalibrated · matching active</dd>
          </div>
        </dl>
      </section>
      <AIControls />
      <div className="notice">
        <h2>Current limitations</h2>
        <p>
          Optional source-verified local AI suggestions use add-only merging and
          deadlines. Semantic thresholds remain uncalibrated. Generic topics,
          semantic-only matches, and judgment-dependent items remain yellow.
          Sponsor materials and reviewer feedback are excluded from matching.
          Exports retain raw screening colors and reviewer decisions separately.
          The Python socket airlock is active; Offline status shows connection
          evidence and its verification boundaries.{" "}
          {status.sponsor_evaluation_state === "complete"
            ? "The frozen evaluation missed accuracy targets; see the scorecard before relying on results."
            : "The scorecard shows evaluation availability and any measured results."}
        </p>
      </div>
    </>
  );
}
