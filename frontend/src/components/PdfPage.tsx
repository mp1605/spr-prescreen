import { useState } from "react";
import type { Finding, SourceUnit } from "../api/workflow";

export function PdfPage({
  unit,
  findings,
  active,
  base,
  anchors,
  rotation = 0,
}: {
  unit: SourceUnit;
  findings: Finding[];
  active: string | undefined;
  base: string;
  rotation?: number;
  anchors?: Record<string, { page: number; x: number; y: number }>;
}) {
  const [failed, setFailed] = useState(false),
    flags = findings.filter((flag) => flag.location.page === unit.page);
  const width =
    (rotation === 90 || rotation === 270 ? unit.height : unit.width) ?? 0;
  const height =
    (rotation === 90 || rotation === 270 ? unit.width : unit.height) ?? 0;
  const transform =
    rotation === 90
      ? `translate(${unit.height} 0) rotate(90)`
      : rotation === 180
        ? `translate(${unit.width} ${unit.height}) rotate(180)`
        : rotation === 270
          ? `translate(0 ${unit.width}) rotate(270)`
          : undefined;
  return (
    <section className="pdf-page">
      <div className="page-label">
        PAGE {unit.page} · {width.toFixed(0)} × {height.toFixed(0)} pt
      </div>
      {failed ? (
        <div className="notice error" role="alert">
          Page image unavailable. Extracted text:<pre>{unit.text}</pre>
          <button className="text-button" onClick={() => setFailed(false)}>
            Retry page image
          </button>
        </div>
      ) : (
        <div className="pdf-canvas">
          <img
            src={`${base}/pages/${unit.page}.png`}
            width={width}
            height={height}
            alt={`Document page ${unit.page}. Extracted text is available below.`}
            loading="lazy"
            onError={() => setFailed(true)}
          />
          <svg
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            className="pdf-overlay"
            role="img"
            aria-label={`Evidence on page ${unit.page}`}
          >
            <g transform={transform}>
              {!anchors &&
                flags.flatMap((flag) =>
                  (flag.location.bbox ?? []).map((box, index) => (
                    <rect
                      key={`${flag.finding_id}-${index}`}
                      data-evidence={flag.finding_id}
                      className={`${flag.color} ${flag.finding_id === active ? "selected" : ""}`}
                      x={box[0]}
                      y={box[1]}
                      width={box[2] - box[0]}
                      height={box[3] - box[1]}
                    >
                      <title>
                        {flag.items.join(", ")}: {flag.quote}
                      </title>
                    </rect>
                  )),
                )}
              {anchors &&
                Object.entries(anchors)
                  .filter(([, a]) => a.page === unit.page)
                  .map(([id, a]) => (
                    <rect
                      key={id}
                      data-evidence={id}
                      x={a.x - 4}
                      y={a.y - 4}
                      width={12}
                      height={18}
                      className={`word-anchor ${id === active ? "selected" : ""}`}
                    >
                      <title>Selected source evidence</title>
                    </rect>
                  ))}
            </g>
          </svg>
        </div>
      )}
      <details className="pdf-text">
        <summary>Accessible page text</summary>
        <pre>
          {unit.text || "No readable text could be extracted from this page."}
        </pre>
      </details>
    </section>
  );
}
