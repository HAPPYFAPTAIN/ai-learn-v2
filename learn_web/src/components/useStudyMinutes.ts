import { useEffect } from "react";
import { endpoints } from "../api";
import { useQueryClient } from "@tanstack/react-query";
import { key } from "../query";

export function useStudyMinutes(projectId: number, nodeId?: number) {
  const client = useQueryClient();
  useEffect(() => {
    if (!projectId || !nodeId || __DEMO__) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let active = true;
    let remaining = 60_000;
    let started = 0;
    let inFlight = false;
    const schedule = () => {
      if (inFlight || !active || document.visibilityState !== "visible") return;
      started = performance.now();
      timer = setTimeout(async () => {
        timer = undefined;
        remaining = 60_000;
        inFlight = true;
        // No automatic retry on uncertain writes: never double-count minutes.
        try {
          await endpoints.recordMinutes(projectId, nodeId);
          void client.invalidateQueries({
            queryKey: key("summary", projectId),
          });
        } catch {
          /* keep studying; failed writes do not block the lesson */
        }
        inFlight = false;
        schedule();
      }, remaining);
    };
    const visibility = () => {
      if (timer) {
        clearTimeout(timer);
        timer = undefined;
        remaining = Math.max(1, remaining - (performance.now() - started));
      }
      schedule();
    };
    document.addEventListener("visibilitychange", visibility);
    schedule();
    return () => {
      active = false;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [projectId, nodeId, client]);
}
