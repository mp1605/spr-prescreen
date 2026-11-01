import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { send, type ReviewEvent, type ReviewState } from "../api/workflow";

export function activeEvents(events: ReviewEvent[]) {
  const stacks = new Map<string, ReviewEvent[]>();
  for (const event of events) {
    const key = event.finding_id ?? "$paper",
      stack = stacks.get(key) ?? [];
    if (event.action === "undo") stack.pop();
    else stack.push(event);
    stacks.set(key, stack);
  }
  return [...stacks.values()].flatMap((stack) =>
    stack.length ? [stack[stack.length - 1]] : [],
  );
}
type Action = {
  action: ReviewEvent["action"];
  finding_id?: string | null;
  reason?: string;
  target_event?: string;
};
type Command = Action & { revision: number; reviewer: string };

export function useReviewActions(
  base: string,
  state: ReviewState | undefined,
  reviewer: string,
) {
  const client = useQueryClient(),
    key = ["decisions", base];
  const [toast, setToast] = useState("");
  const mutation = useMutation({
    mutationFn: (command: Command) =>
      send<ReviewState>(`${base}/decisions`, command),
    onMutate: async (action) => {
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<ReviewState>(key);
      if (
        previous &&
        action.action !== "approve" &&
        !(action.action === "undo" && previous.approved && !action.finding_id)
      ) {
        const event: ReviewEvent = {
          event_id: "pending",
          entry_id: "",
          finding_id: action.finding_id ?? null,
          action: action.action,
          reason: action.reason ?? null,
          reviewer: action.reviewer,
          utc: new Date().toISOString(),
          target_event: action.target_event ?? null,
          feedback: null,
        };
        const events = [...previous.events, event],
          active = activeEvents(events);
        client.setQueryData<ReviewState>(key, {
          ...previous,
          revision: previous.revision + 1,
          events,
          decisions: Object.fromEntries(
            active
              .filter((value) => value.finding_id)
              .map((value) => [value.finding_id!, value]),
          ),
          inspected: active.some((value) =>
            ["inspect", "approve"].includes(value.action),
          ),
          feedback_examples: previous.feedback_examples.filter((example) =>
            active.some(
              (event) =>
                event.finding_id === example.finding_id &&
                event.feedback?.polarity === example.polarity,
            ),
          ),
        });
      }
      return { previous };
    },
    onError: (error, _action, context) => {
      if (context?.previous) client.setQueryData(key, context.previous);
      setToast(`Not saved: ${error.message}`);
      void client.invalidateQueries({ queryKey: key });
    },
    onSuccess: (value, action) => {
      client.setQueryData(key, value);
      setToast(
        value.storage_error
          ? "Review saved. Document folder needs updating; see the storage message."
          : action.action === "approve"
            ? "Reviewed and approved. Document saved in Approved."
            : action.action === "undo"
              ? "Decision undone. Audit history retained."
              : action.action === "inspect"
                ? "Source inspection recorded."
                : action.action === "accept"
                  ? "Flag accepted."
                  : "Flag overridden. Raw finding retained.",
      );
      void client.invalidateQueries({ queryKey: ["batches"] });
      void client.invalidateQueries({ queryKey: ["batch-folders"] });
      void client.invalidateQueries({ queryKey: ["item-index"] });
      void client.invalidateQueries({ queryKey: ["item-page"] });
    },
  });
  const activeIds = new Set(
    state ? activeEvents(state.events).map((event) => event.event_id) : [],
  );
  const undoable = state?.events
    .slice()
    .reverse()
    .find(
      (event) =>
        activeIds.has(event.event_id) && event.reviewer === reviewer.trim(),
    );
  function save(action: Action) {
    if (!reviewer.trim()) {
      setToast("Enter your reviewer name before recording a decision.");
      return;
    }
    if (!state || mutation.isPending) return;
    mutation.mutate({
      ...action,
      revision: state.revision,
      reviewer: reviewer.trim(),
    });
  }
  function undo() {
    if (undoable)
      save({
        action: "undo",
        finding_id: undoable.finding_id,
        target_event: undoable.event_id,
      });
  }
  return { save, undo, undoable, toast, busy: mutation.isPending };
}
