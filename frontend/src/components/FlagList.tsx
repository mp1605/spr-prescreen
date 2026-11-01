import type { RefObject } from "react";
import type { Finding, Paper, ReviewState } from "../api/workflow";
import type { RuleItem } from "../api/client";
import { FlagCard } from "./FlagCard";
interface Props {
  flags: Finding[];
  index: number;
  state: ReviewState;
  items: Map<string, RuleItem>;
  select: (index: number) => void;
  save: (action: { action: "accept" | "override"; finding_id: string }) => void;
  reviewer: string;
  busy: boolean;
  openOverride: () => void;
  paneRef: RefObject<HTMLDivElement>;
  paper: Paper;
}
export function FlagList({
  flags,
  index,
  state,
  items,
  select,
  save,
  reviewer,
  busy,
  openOverride,
  paneRef,
  paper,
}: Props) {
  return (
    <section className="flags-panel">
      <div className="pane-heading">
        <h2>
          Flag review <span className="count-pill">{flags.length}</span>
        </h2>
        <span>List 1 → List 2</span>
      </div>
      <div className="flags-scroll" ref={paneRef}>
        {flags.length ? (
          (["list1", "list2"] as const).map((list) => (
            <div key={list}>
              <h3 className="flag-group">
                {list === "list1" ? "01 · List 1" : "02 · List 2"}
                <span>
                  {flags.filter((flag) => flag.list === list).length} flags
                </span>
              </h3>
              {flags.map(
                (flag, position) =>
                  flag.list === list && (
                    <FlagCard
                      key={flag.finding_id}
                      flag={flag}
                      index={position}
                      active={position === index}
                      decision={state.decisions[flag.finding_id]}
                      items={items}
                      select={() => select(position)}
                      accept={() =>
                        save({
                          action: "accept",
                          finding_id: flag.finding_id,
                        })
                      }
                      override={() => {
                        select(position);
                        if (reviewer.trim()) openOverride();
                        else
                          save({
                            action: "override",
                            finding_id: flag.finding_id,
                          });
                      }}
                      busy={busy || !reviewer.trim()}
                    />
                  ),
              )}
            </div>
          ))
        ) : (
          <div className="queue-empty">
            <h3>
              {paper.incomplete_reasons.length
                ? "No extracted flags · source incomplete"
                : "No flags found"}
            </h3>
            <p>List 1 and List 2 checked. A reviewer still decides.</p>
            <p>Inspect the source, then record that inspection above.</p>
          </div>
        )}
      </div>
    </section>
  );
}
