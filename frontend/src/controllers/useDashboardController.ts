import { useCallback, useRef, useState } from "react";
import { api } from "../api";
import { remoteResourceStatus } from "../remoteResource";
import type { FactoryDashboard } from "../types";
import { usePolling } from "../usePolling";

export function useDashboardController(enabled: boolean) {
  const [dashboard, setDashboard] = useState<FactoryDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<Promise<void> | null>(null);

  const refresh = useCallback((): Promise<void> => {
    if (request.current) return request.current;
    request.current = api<FactoryDashboard>("/api/dashboard")
      .then((loaded) => {
        setDashboard(loaded);
        setError(null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        request.current = null;
      });
    return request.current;
  }, []);

  const retry = useCallback(() => {
    if (dashboard === null) setError(null);
    return refresh();
  }, [dashboard, refresh]);

  usePolling(refresh, 5000, enabled);

  return {
    dashboard,
    error,
    status: remoteResourceStatus(dashboard, error),
    refresh,
    retry,
  };
}
