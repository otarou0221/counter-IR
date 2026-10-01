export type FieldRoute =
  | { page: "field"; view: "map" }
  | { page: "field"; view: "camera"; cameraId: string };

export type AppRoute = FieldRoute | { page: "debug" } | { page: "settings" };
export type NavigationTarget = "map" | "field" | "settings" | "debug";

export const fieldMapRoute: FieldRoute = { page: "field", view: "map" };

export function parseAppPath(pathname: string): AppRoute {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (normalized === "/field/map") return fieldMapRoute;
  if (normalized === "/settings") return { page: "settings" };
  if (normalized === "/debug") return { page: "debug" };

  const cameraMatch = normalized.match(/^\/field\/camera\/([^/]+)$/);
  if (cameraMatch) {
    try {
      const cameraId = decodeURIComponent(cameraMatch[1]);
      if (cameraId) return { page: "field", view: "camera", cameraId };
    } catch {
      // 不正なURLエンコードは安全な初期画面へ戻す。
    }
  }
  return fieldMapRoute;
}

export function appRoutePath(route: AppRoute): string {
  if (route.page === "field") {
    return route.view === "map"
      ? "/field/map"
      : `/field/camera/${encodeURIComponent(route.cameraId)}`;
  }
  return `/${route.page}`;
}

export function navigationTargetForRoute(route: AppRoute): NavigationTarget {
  if (route.page !== "field") return route.page;
  return route.view === "map" ? "map" : "field";
}

export function routeForNavigationTarget(
  target: NavigationTarget,
  selectedCameraId: string,
): AppRoute {
  if (target === "map") return fieldMapRoute;
  if (target === "field") {
    return selectedCameraId
      ? { page: "field", view: "camera", cameraId: selectedCameraId }
      : fieldMapRoute;
  }
  return { page: target };
}
