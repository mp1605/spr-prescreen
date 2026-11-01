import { useEffect, useRef } from "react";
import type { DocumentView, Finding } from "../api/workflow";
import { useQuery } from "@tanstack/react-query";
import { PdfPage } from "./PdfPage";
import { WordLayoutView, loadLayout } from "./WordLayoutView";

export function DocumentViewer({
  document,
  findings,
  active,
  base,
  pulse,
}: {
  document: DocumentView;
  findings: Finding[];
  active: string | undefined;
  base: string;
  pulse: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const word = document.units.every((unit) => unit.page === null);
  const layout = useQuery({
    queryKey: ["word-layout", base],
    queryFn: () => loadLayout(base),
    enabled: word,
    retry: false,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (!active) return;
    const target = Array.from(
      container.current?.querySelectorAll<HTMLElement | SVGElement>(
        "[data-evidence]",
      ) ?? [],
    ).find((element) => element.dataset.evidence?.split(" ").includes(active));
    const pane = container.current;
    if (target && pane) {
      const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth";
      const box = target.getBoundingClientRect(),
        bounds = pane.getBoundingClientRect();
      pane.scrollTo({
        top:
          pane.scrollTop +
          box.top -
          bounds.top -
          pane.clientHeight / 2 +
          box.height / 2,
        behavior,
      });
      // On a stacked mobile layout, bring the document above the flag list into view.
      if (pulse > 0 && matchMedia("(max-width: 900px)").matches)
        pane.scrollIntoView({ behavior, block: "start" });
      target.classList.remove("evidence-pulse");
      requestAnimationFrame(() => target.classList.add("evidence-pulse"));
    }
  }, [active, document, pulse, layout.data]);
  return (
    <div
      className="document-scroll"
      ref={container}
      tabIndex={0}
      role="region"
      aria-label="Source document and highlights"
    >
      {word ? (
        <WordLayoutView
          layout={layout}
          document={document}
          findings={findings}
          active={active}
          base={base}
        />
      ) : (
        document.units.map((unit) => (
          <PdfPage
            key={unit.unit_id}
            unit={unit}
            rotation={document.page_rotations?.[unit.page ?? 0] ?? 0}
            findings={findings}
            active={active}
            base={base}
          />
        ))
      )}
    </div>
  );
}
