import { useEffect } from "react";

export function useReviewKeys(
  actions: Record<string, () => void>,
  paused: boolean,
) {
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        paused ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.repeat ||
        target?.closest(
          "input, textarea, select, [contenteditable='true'], dialog[open]",
        )
      )
        return;
      const action = actions[event.key.toLowerCase()];
      if (action) {
        event.preventDefault();
        action();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [actions, paused]);
}
