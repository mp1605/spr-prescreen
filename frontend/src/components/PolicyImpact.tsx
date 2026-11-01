import { useQuery } from "@tanstack/react-query";
import { adminRequest, type Preview } from "../api/admin";
import type { Paper } from "../api/workflow";
function Evidence({ paper, name }: { paper: Paper | null; name: string }) {
  return (
    <div>
      <h4>{name}</h4>
      {!paper ? (
        <p>Not yet compared</p>
      ) : (
        <>
          <p>
            {paper.color.toUpperCase()} · {paper.flag_count.total} flags
          </p>
          {paper.findings.map((flag) => (
            <div className="impact-flag" key={flag.finding_id}>
              <strong>
                {flag.color.toUpperCase()} · {flag.items.join(" · ")}
              </strong>
              <blockquote>{flag.quote}</blockquote>
              <p>{flag.reason}</p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
export function PolicyImpact({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ["policy-preview", id],
    queryFn: () => adminRequest<Preview>(`/rules/previews/${id}`),
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.state ?? "queued")
        ? 1000
        : false,
  });
  if (!query.data)
    return (
      <p role="status">
        {query.error
          ? "Could not load the impact preview."
          : "Loading impact preview…"}
        <button className="text-button" onClick={() => void query.refetch()}>
          Retry
        </button>
      </p>
    );
  const preview = query.data;
  return (
    <section className="policy-impact" aria-label="Impact preview">
      <h3>Impact preview · {preview.state}</h3>
      <p>{preview.message}</p>
      <p className="subtle">
        Only the uploaded files were scanned. Sponsor recall and accuracy are
        not measured.
      </p>
      <div className="impact-summary">
        {preview.entries.filter((e) => e.after).length}/{preview.entries.length}{" "}
        compared · {preview.entries.filter((e) => e.changed).length} changed ·{" "}
        {
          preview.entries.filter((e) => e.before?.color !== e.after?.color)
            .length
        }{" "}
        color changes
      </div>
      {preview.entries.map((entry, index) => (
        <details key={index} className="impact-entry">
          <summary>
            {entry.file_name} · {entry.before?.color.toUpperCase() ?? "PENDING"}{" "}
            → {entry.after?.color.toUpperCase() ?? "PENDING"} ·{" "}
            {entry.changed
              ? "Changed"
              : entry.after
                ? "No change"
                : entry.message}
          </summary>
          <small>
            Source SHA-256 <code>{entry.sha256}</code>
          </small>
          <div className="policy-diff">
            <Evidence paper={entry.before} name="Active policy" />
            <Evidence paper={entry.after} name="Draft policy" />
          </div>
        </details>
      ))}
    </section>
  );
}
