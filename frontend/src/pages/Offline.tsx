import { useQuery } from "@tanstack/react-query";
import { RefreshCw, WifiOff } from "lucide-react";
import { get } from "../api/client";
import { QueryState } from "../components/QueryState";

interface OfflineStatus {
  airlock_installed: boolean;
  blocked_attempts: number;
  listeners: {
    port: number;
    address: string;
    loopback: boolean;
    process: string;
    evidence: string;
  }[];
  listener_inspection: "available" | "partial" | "unavailable";
  models_on_disk: {
    ready: boolean;
    files: number;
    bytes: number;
    message: string;
  };
  ai_reachable: boolean;
  bundled_ai_present: boolean;
  bundled_ai_bytes: number;
  guard_scope: string;
  native_scope: string;
}
export function Offline() {
  const query = useQuery({
    queryKey: ["offline"],
    queryFn: () => get<OfflineStatus>("/api/system/offline"),
  });
  if (!query.data)
    return (
      <QueryState error={query.error} retry={() => void query.refetch()} />
    );
  const data = query.data;
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Offline status</h1>
        </div>
        <button
          className="outline-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw size={16} />
          {query.isFetching ? "Refreshing…" : "Refresh offline status"}
        </button>
      </div>
      {query.error && (
        <p className="notice error" role="alert">
          Refresh failed. Showing the last received status.
        </p>
      )}
      <section className="panel">
        <h2>
          <WifiOff size={20} /> Python network guard
        </h2>
        <dl className="status-list">
          <div>
            <dt>Guard</dt>
            <dd>
              {data.airlock_installed
                ? "Active · loopback only"
                : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt>Blocked calls</dt>
            <dd>{data.blocked_attempts} · backend and parser workers</dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>{data.guard_scope}</dd>
          </div>
          <div>
            <dt>Local AI endpoint</dt>
            <dd>
              {data.ai_reachable
                ? "Reachable at 127.0.0.1:11434"
                : "Unavailable · AI remains optional"}
            </dd>
          </div>
        </dl>
        <p className="subtle">
          The counter includes explicit guard tests. A blocked call is refused
          before external DNS resolution or connection.
        </p>
      </section>
      <section className="panel">
        <h2>Observed TCP listeners</h2>
        <p>
          {data.listener_inspection === "available"
            ? "Operating-system observations for this backend, local AI service and their child processes."
            : data.listener_inspection === "partial"
              ? "Relevant port listeners were observed by the OS. Child-process inspection is unavailable in this environment."
              : "OS listener inspection is unavailable. Request-socket information is shown when available."}
        </p>
        {data.listeners.length ? (
          <dl className="status-list">
            {data.listeners.map((entry, index) => (
              <div key={index}>
                <dt>
                  {entry.process} · {entry.port}
                </dt>
                <dd>
                  {entry.address}:{entry.port} ·{" "}
                  {entry.loopback
                    ? "Loopback"
                    : "NON-LOOPBACK · inspect service configuration"}{" "}
                  · {entry.evidence.replaceAll("_", " ")}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>No matching listener was returned by the OS inspection.</p>
        )}
      </section>
      <section className="panel">
        <h2>Screening model files</h2>
        <p>{data.models_on_disk.message}</p>
        <dl className="status-list">
          <div>
            <dt>Files present</dt>
            <dd>{data.models_on_disk.files}</dd>
          </div>
          <div>
            <dt>Local size</dt>
            <dd>{(data.models_on_disk.bytes / 1024 / 1024).toFixed(1)} MB</dd>
          </div>
          <div>
            <dt>Bundled Qwen files</dt>
            <dd>
              {data.bundled_ai_present
                ? `${(data.bundled_ai_bytes / 1024 / 1024 / 1024).toFixed(2)} GiB present · size checked`
                : "Not present or size mismatch · optional AI unavailable"}
            </dd>
          </div>
          <div>
            <dt>Runtime downloads</dt>
            <dd>
              Disabled · model and package preparation is a separate explicit
              step
            </dd>
          </div>
        </dl>
      </section>
      <div className="notice">
        <h2>Verification boundaries</h2>
        <p>{data.native_scope}</p>
        <p>
          This screen does not measure Wi-Fi state or claim that every process
          on the computer is isolated. The portable bundle includes local
          wheels, model files and built web assets. Physical Wi-Fi-off and
          second-machine checks remain separate acceptance steps.
        </p>
      </div>
    </>
  );
}
