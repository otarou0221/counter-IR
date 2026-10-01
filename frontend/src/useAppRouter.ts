import { useCallback, useEffect, useState } from "react";
import {
  appRoutePath,
  parseAppPath,
  type AppRoute,
} from "./routes";

type NavigateOptions = { replace?: boolean };

function currentRoute(): AppRoute {
  return parseAppPath(window.location.pathname);
}

export function useAppRouter() {
  const [route, setRoute] = useState<AppRoute>(currentRoute);

  const applyRoute = useCallback((nextRoute: AppRoute) => {
    setRoute(nextRoute);
  }, []);

  const navigate = useCallback((nextRoute: AppRoute, options: NavigateOptions = {}) => {
    const nextPath = appRoutePath(nextRoute);
    if (window.location.pathname !== nextPath || window.location.search || window.location.hash) {
      const method = options.replace ? "replaceState" : "pushState";
      window.history[method](null, "", nextPath);
    }
    applyRoute(nextRoute);
  }, [applyRoute]);

  useEffect(() => {
    const syncFromBrowser = () => {
      const nextRoute = currentRoute();
      const canonicalPath = appRoutePath(nextRoute);
      if (window.location.pathname !== canonicalPath) {
        window.history.replaceState(null, "", canonicalPath);
      }
      applyRoute(nextRoute);
    };
    syncFromBrowser();
    window.addEventListener("popstate", syncFromBrowser);
    return () => window.removeEventListener("popstate", syncFromBrowser);
  }, [applyRoute]);

  return { route, navigate };
}
