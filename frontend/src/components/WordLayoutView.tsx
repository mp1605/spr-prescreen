import type { UseQueryResult } from "@tanstack/react-query";
import type { DocumentView, Finding } from "../api/workflow";
import { PdfPage } from "./PdfPage";
import { WordParagraph } from "./WordParagraph";

interface WordLayout extends DocumentView {
  identity: string;
  anchors: Record<string, { page: number; x: number; y: number }>;
  unmapped: string[];
  seconds: number;
}
export async function loadLayout(base: string): Promise<WordLayout> {
  const response = await fetch(`${base}/layout`, {
    signal: AbortSignal.timeout(80000),
  });
  const data: unknown = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data === "object" &&
      data &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : "Word preview could not be prepared.",
    );
  return data as WordLayout;
}
export function WordLayoutView({
  layout,
  document,
  findings,
  active,
  base,
}: {
  layout: UseQueryResult<WordLayout, Error>;
  document: DocumentView;
  findings: Finding[];
  active: string | undefined;
  base: string;
}) {
  if (layout.isPending)
    return (
      <div className="notice" role="status">
        Preparing original Word pages… This happens once when you open the
        document; scanning is already complete.
      </div>
    );
  if (layout.isError)
    return (
      <div className="notice error" role="alert">
        <p>{layout.error.message}</p>
        <button
          className="outline-button"
          onClick={() => void layout.refetch()}
        >
          Retry Word preview
        </button>{" "}
        <a href={`${base}/original`}>Download original Word file</a>
        <p>
          Source evidence remains available in the flag list. The highlighted
          DOCX download preserves its native formatting.
        </p>
      </div>
    );
  const data = layout.data;
  const unmapped = findings.filter((f) => data.unmapped.includes(f.finding_id));
  return (
    <>
      {data.units.map((unit) => (
        <PdfPage
          key={unit.unit_id}
          unit={unit}
          findings={[]}
          active={active}
          base={`${base}/layout/${data.identity}`}
          anchors={data.anchors}
        />
      ))}
      {!!unmapped.length && (
        <section className="off-page-evidence">
          <h3>Evidence outside the page preview</h3>
          <p>
            Comments, hidden text, or unsupported Word elements may not have a
            visible page anchor. These excerpts retain their source paragraph
            locations.
          </p>
          {document.units
            .filter((unit) =>
              unmapped.some((f) => f.location.paragraph === unit.paragraph),
            )
            .map((unit) => (
              <WordParagraph
                key={unit.unit_id}
                unit={unit}
                findings={unmapped}
                active={active}
              />
            ))}
        </section>
      )}
    </>
  );
}
