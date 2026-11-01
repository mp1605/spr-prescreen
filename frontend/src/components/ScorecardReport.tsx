import { rate, type EvaluationReport } from "../api/evaluation";

export function ScorecardReport({ report }: { report: EvaluationReport }) {
  const failures = [
    report.trigger_count > report.matched_triggers
      ? `${report.trigger_count - report.matched_triggers} expected triggers were not matched.`
      : "",
    report.false_alarms
      ? `${report.false_alarms} predicted passages had no matching reference trigger.`
      : "",
    report.paper_color_accuracy < 1
      ? "Some paper colors disagree with the reference labels."
      : "",
    report.flag_color_accuracy !== null && report.flag_color_accuracy < 1
      ? "Some matched flag colors disagree with reference labels."
      : "",
    report.incomplete_papers
      ? `${report.incomplete_papers} sources were incomplete.`
      : "",
  ].filter(Boolean);
  return (
    <>
      {report.kind === "format_contract" && (
        <p className="notice">
          Format contract only. These numbers do not measure scanner accuracy.
        </p>
      )}
      <div className="metric-grid">
        {[
          ["Trigger recall", rate(report.trigger_recall)],
          ["List 1 recall", rate(report.list1_recall)],
          ["List 2 recall", rate(report.list2_recall)],
          ["Paper color accuracy", rate(report.paper_color_accuracy)],
          ["Flag color accuracy", rate(report.flag_color_accuracy)],
          ["Matched item Jaccard", rate(report.item_accuracy)],
        ].map(([label, value]) => (
          <article className="panel" key={label}>
            <h2>{label}</h2>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <section className="panel">
        <h2>Paper color comparison</h2>
        <p>
          {report.paper_count} papers · {report.matched_triggers}/
          {report.trigger_count} triggers matched. Rows are reference colors;
          columns are predicted colors.
        </p>
        <div className="table-scroll">
          <table className="queue-table">
            <caption>Paper color confusion matrix</caption>
            <thead>
              <tr>
                <th scope="col">Reference / predicted</th>
                {["green", "yellow", "red"].map((c) => (
                  <th scope="col" key={c}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {["green", "yellow", "red"].map((c) => (
                <tr key={c}>
                  <th scope="row">{c}</th>
                  {["green", "yellow", "red"].map((p) => (
                    <td key={p}>{report.confusion[c][p]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>False alarms and decoys</h2>
        <dl className="status-list">
          {[
            ["Unmatched predicted passages", report.false_alarms],
            ["Green papers with findings", report.greens_wrongly_flagged],
            [
              "Decoys flagged",
              `${report.decoys_flagged}/${report.decoy_count}`,
            ],
            [
              "Reference-paper false alarms",
              report.reference_paper_count
                ? report.false_alarms_on_reference_papers
                : "Not measured · no reference papers",
            ],
            ["Incomplete sources", report.incomplete_papers],
            ["Weighted cost", report.weighted_cost],
          ].map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <p>{report.cost_assumption}</p>
      </section>
      <section className="panel">
        <h2>Where it fails</h2>
        {failures.length ? (
          <ul>
            {failures.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        ) : (
          <p>
            No failures observed in this evaluated input set. This says nothing
            about other papers.
          </p>
        )}
        {report.cases
          .filter(
            (c) =>
              c.missed.length ||
              c.false_alarms.length ||
              c.decoy_hits.length ||
              c.expected_color !== c.actual_color,
          )
          .map((c) => (
            <details key={c.case_id}>
              <summary>
                {c.case_id} · {c.expected_color} reference → {c.actual_color}{" "}
                predicted
              </summary>
              {c.missed.map((t) => (
                <div key={t.tag}>
                  <h3>
                    Missed {t.tag} · {t.items.join(" · ")}
                  </h3>
                  <blockquote>{t.quote}</blockquote>
                  <p>{t.reason}</p>
                </div>
              ))}
              {c.false_alarms.map((f, i) => (
                <div key={i}>
                  <h3>Unmatched finding · {f.items.join(" · ")}</h3>
                  <blockquote>{f.quote}</blockquote>
                </div>
              ))}
              {c.decoy_hits.map((q, i) => (
                <div key={i}>
                  <h3>Decoy flagged</h3>
                  <blockquote>{q}</blockquote>
                </div>
              ))}
            </details>
          ))}
      </section>
      <section className="panel">
        <h2>Timing and provenance</h2>
        <dl className="status-list">
          <div>
            <dt>AI off seconds per paper</dt>
            <dd>
              {report.seconds_per_paper_ai_off?.toFixed(2) ?? "Not defined"}
            </dd>
          </div>
          <div>
            <dt>AI attempted seconds per paper</dt>
            <dd>
              {report.seconds_per_paper_ai_on?.toFixed(2) ?? "Not defined"}
            </dd>
          </div>
          <div>
            <dt>Rules versions</dt>
            <dd>{report.rules_versions.join(", ")}</dd>
          </div>
        </dl>
        <p>
          Timing belongs to this evaluated set. It is not a promise for other
          input sizes or machines.
        </p>
        <details>
          <summary>Matching policy</summary>
          <p>{report.matching_policy}</p>
        </details>
      </section>
    </>
  );
}
