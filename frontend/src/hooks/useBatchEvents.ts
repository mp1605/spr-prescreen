import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function useBatchEvents(runId: string | undefined, active: boolean) {
  const client = useQueryClient();
  const [connection, setConnection] = useState("Waiting for batch");
  useEffect(() => {
    if (!runId || !active) {
      setConnection("Progress saved locally");
      return;
    }
    const events = new EventSource(`/api/batches/${runId}/events`);
    let timer: ReturnType<typeof setTimeout> | undefined;
    events.onopen = () => setConnection("Live progress connected");
    events.onerror = () => {
      setConnection("Reconnecting · polling continues");
    };
    events.addEventListener("progress", (event: MessageEvent<string>) => {
      clearTimeout(timer);
      timer = setTimeout(
        () => void client.invalidateQueries({ queryKey: ["batches"] }),
        80,
      );
      const data = JSON.parse(event.data) as { terminal: boolean };
      if (data.terminal) {
        events.close();
        setConnection("Batch finished · progress saved");
      }
    });
    return () => {
      events.close();
      clearTimeout(timer);
    };
  }, [runId, active, client]);
  return connection;
}
