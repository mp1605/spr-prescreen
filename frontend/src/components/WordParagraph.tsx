import type { Finding, SourceUnit } from "../api/workflow";

export function WordParagraph({
  unit,
  findings,
  active,
}: {
  unit: SourceUnit;
  findings: Finding[];
  active: string | undefined;
}) {
  const flags = findings.filter(
    (flag) => flag.location.paragraph === unit.paragraph,
  );
  const characters = Array.from(unit.text);
  const boundaries = [
    ...new Set([
      0,
      characters.length,
      ...flags.flatMap((flag) => [
        flag.location.char_start,
        flag.location.char_end,
      ]),
    ]),
  ].sort((a, b) => a - b);
  const content = boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1],
      matches = flags.filter(
        (flag) =>
          flag.location.char_start < end && flag.location.char_end > start,
      );
    const text = characters.slice(start, end).join(""),
      selected = matches.some((flag) => flag.finding_id === active);
    return matches.length ? (
      <mark
        key={start}
        data-evidence={matches.map((flag) => flag.finding_id).join(" ")}
        className={`${matches.some((flag) => flag.color === "red") ? "red" : "yellow"} ${selected ? "selected" : ""}`}
      >
        {text}
      </mark>
    ) : (
      <span key={start}>{text}</span>
    );
  });
  return (
    <section className="word-paragraph">
      <div className="paragraph-locator">
        ¶ {unit.paragraph}{" "}
        {unit.part !== "word/document.xml" && (
          <span>· {unit.part.replace("word/", "")}</span>
        )}
      </div>
      {unit.heading && unit.text === unit.heading ? (
        <h3>{content}</h3>
      ) : (
        <p>
          {content.length ? (
            content
          ) : (
            <span className="subtle">Empty paragraph</span>
          )}
        </p>
      )}
      {unit.excluded.length > 0 && (
        <small className="subtle">
          Documented noise excluded from screening; source shown unchanged.
        </small>
      )}
    </section>
  );
}
