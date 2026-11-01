import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, RefreshCw, BarChart3 } from "lucide-react";
import { get } from "../api/client";
import type { ScorecardStatus } from "../api/evaluation";
import { ScorecardReport } from "../components/ScorecardReport";
import "../workflow.css";

export function Scorecard() {
  const [split, setSplit] = useState<"dev" | "holdout">("dev");
  const tabs = useRef<HTMLDivElement>(null);
  const query = useQuery({
    queryKey: ["scorecard", split],
    queryFn: () => get<ScorecardStatus>(`/api/evaluation/scorecard/${split}`),
  });
  function download() {
    if (!query.data) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(query.data, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `evaluation-${split}-${query.data.report ? "report" : "status"}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Evaluation scorecard</h1>
          <p>Saved evaluation results</p>
        </div>
        <button
          className="outline-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw size={16} />
          Refresh evaluation status
        </button>
      </div>
      <div
        className="scorecard-tabs"
        role="tablist"
        aria-label="Evaluation split"
        ref={tabs}
        onKeyDown={(e) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key))
            return;
          e.preventDefault();
          const next =
            e.key === "Home"
              ? "dev"
              : e.key === "End"
                ? "holdout"
                : split === "dev"
                  ? "holdout"
                  : "dev";
          setSplit(next);
          tabs.current
            ?.querySelector<HTMLButtonElement>(`#tab-${next}`)
            ?.focus();
        }}
      >
        {(["dev", "holdout"] as const).map((value) => (
          <button
            id={`tab-${value}`}
            key={value}
            role="tab"
            aria-controls={`panel-${value}`}
            aria-selected={split === value}
            tabIndex={split === value ? 0 : -1}
            onClick={() => setSplit(value)}
          >
            {value === "dev" ? "Development" : "Holdout"}
          </button>
        ))}
      </div>
      <section
        id={`panel-${split}`}
        role="tabpanel"
        aria-labelledby={`tab-${split}`}
        tabIndex={0}
      >
        {query.isPending ? (
          <p className="notice" role="status">
            Reading evaluation status…
          </p>
        ) : query.error ? (
          <div className="notice error" role="alert">
            <h2>Evaluation status unavailable</h2>
            <p>{query.error.message}</p>
            <button onClick={() => void query.refetch()}>Try again</button>
          </div>
        ) : (
          query.data && (
            <>
              {!query.data.report ? (
                <>
                  <section className="panel evaluation-boundary">
                    <BarChart3 size={28} aria-hidden="true" />
                    <h2>Evaluation deferred</h2>
                    <p>{query.data.message}</p>
                    <p>
                      Switching tabs reads status only. It does not open answer
                      keys or start a holdout run.
                    </p>
                  </section>
                  <div className="metric-grid">
                    {[
                      "List 1 trigger recall",
                      "List 2 trigger recall",
                      "Paper and flag colors",
                      "False alarms and decoys",
                      "AI on / off timing",
                      "Missed trigger evidence",
                    ].map((label) => (
                      <article className="panel" key={label}>
                        <h2>{label}</h2>
                        <strong>Not measured</strong>
                      </article>
                    ))}
                  </div>
                  <section className="panel">
                    <h2>Why there are no scores yet</h2>
                    <p>
                      This workspace has no published evaluation results.
                      Software checks use official phrases and mechanical format
                      contracts; they do not establish accuracy on research
                      papers.
                    </p>
                    <p>
                      A separately authorized evaluation follows implementation.
                      Missing measurements must not be presented as zero errors
                      or perfect recall.
                    </p>
                  </section>
                </>
              ) : (
                <>
                  <p className="notice" role="status">
                    {query.data.message}
                  </p>
                  <ScorecardReport report={query.data.report} />
                </>
              )}
              <button className="outline-button" onClick={download}>
                <Download size={16} />
                {query.data.report
                  ? "Download evaluation report JSON"
                  : "Download evaluation status JSON"}
              </button>
            </>
          )
        )}
      </section>
    </>
  );
}
