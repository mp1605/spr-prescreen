import type { History } from "../api/admin";
export function PolicyHistory({
  history,
  restore,
  busy,
}: {
  history: History;
  restore: (file: string) => void;
  busy: boolean;
}) {
  return (
    <section className="policy-history" aria-label="Policy version history">
      <h3>Version history</h3>
      <p>
        Restoring a version creates a draft. Validate and preview it before
        publishing the restored contents as a new, audited version.
      </p>
      <div className="version-list">
        {[...history.versions].reverse().map((version) => (
          <div key={version.file}>
            <div>
              <strong>{version.version}</strong>
              <small>
                {version.file} · SHA-256 {version.sha256.slice(0, 16)}…
              </small>
            </div>
            {version.version === history.active.version ? (
              <span className="tag">Active</span>
            ) : version.restorable ? (
              <button
                className="outline-button"
                disabled={busy}
                onClick={() => restore(version.file)}
              >
                Restore as draft
              </button>
            ) : (
              <small>Scaffold · no complete detector runtime</small>
            )}
          </div>
        ))}
      </div>
      <details className="policy-audit">
        <summary>Publication audit · {history.audit.length} events</summary>
        <ol>
          {[...history.audit].reverse().map((event, index) => (
            <li key={index}>
              <strong>
                {event.operation} · {event.version}
              </strong>
              <p>{event.note}</p>
              <small>
                {event.actor} · {new Date(event.utc).toLocaleString()}
              </small>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
