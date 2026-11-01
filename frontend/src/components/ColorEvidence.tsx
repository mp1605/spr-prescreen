import type { ColorAssessment } from "../api/workflow";
import { Triangle, Diamond } from "lucide-react";

const labels: Record<string, string> = {
  quantity: "Quantity",
  unit: "Named unit",
  location: "Location",
  system: "System",
  program: "Program",
  date: "Date",
  future_date: "Future date / month",
  measurement: "Measured detail",
  operational: "Operational context",
  procedure: "Procedure sequence",
  control: "Control reference",
  rank: "Author byline rank",
  actor: "Named component",
  coordination_gap: "Coordination gap",
  origin_release: "Origin / release",
  authority_action: "Authority reference",
  release_event: "Release / response",
  uncertainty: "Uncertain context",
  negation: "Negated disclosure",
};

export function ColorEvidence({
  assessment,
}: {
  assessment: ColorAssessment | null;
}) {
  if (!assessment) return null;
  const specific = assessment.items.filter(
    (item) => item.disposition === "clear",
  ).length;
  return (
    <details className="color-evidence" open={assessment.items.length === 1}>
      <summary>
        Color evidence · {specific} specific /{" "}
        {assessment.items.length - specific} possible
      </summary>
      {assessment.state === "error" && (
        <p className="error">
          Color assessment incomplete. Inspect the source manually.
        </p>
      )}
      <ul>
        {assessment.items.map((item) => {
          const clear = item.disposition === "clear",
            Icon = clear ? Triangle : Diamond;
          return (
            <li key={item.item_id}>
              <div className={`color-item-heading ${clear ? "red" : "yellow"}`}>
                <strong>{item.item_id}</strong>
                <span>
                  <Icon size={12} aria-hidden="true" />
                  {item.item_id.startsWith("L1-")
                    ? "List 1 priority"
                    : clear
                      ? "Specific match"
                      : "Possible match"}
                </span>
              </div>
              <p>{item.reason}</p>
              {item.ai_evidence && (
                <p className="source-fact">
                  <span>AI verified quote</span>
                  <q>{item.ai_evidence.quote}</q>
                </p>
              )}
              {item.rule_anchor && (
                <p className="source-fact">
                  <span>Matched words</span>
                  <q>{item.rule_anchor.text}</q>
                </p>
              )}
              {item.evidence.map((fact, index) => (
                <p className="source-fact" key={`${fact.kind}-${index}`}>
                  <span>{labels[fact.kind] ?? fact.kind}</span>
                  <q>{fact.text}</q>
                </p>
              ))}
            </li>
          );
        })}
      </ul>
      <small>
        Evidence supports screening priority. A reviewer determines
        applicability and release.
      </small>
    </details>
  );
}
