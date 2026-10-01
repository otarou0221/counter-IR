import { useEffect } from "react";

export function usePolling(action: () => Promise<void>, intervalMs: number, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: number | undefined;
    const run = async () => {
      if (document.hidden) return;
      await action();
      if (!cancelled) timer = window.setTimeout(run, intervalMs);
    };
    const handleVisibility = () => {
      if (document.hidden || cancelled) return;
      if (timer !== undefined) window.clearTimeout(timer);
      void run();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    void run();
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", handleVisibility);
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [action, enabled, intervalMs]);
}
