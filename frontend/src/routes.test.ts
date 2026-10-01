import { describe, expect, it } from "vitest";
import {
  appRoutePath,
  fieldMapRoute,
  navigationTargetForRoute,
  parseAppPath,
  routeForNavigationTarget,
} from "./routes";

describe("application routes", () => {
  it.each([
    ["/field/map", { page: "field", view: "map" }],
    ["/field/map/", { page: "field", view: "map" }],
    ["/field/camera/camera_1", { page: "field", view: "camera", cameraId: "camera_1" }],
    ["/settings", { page: "settings" }],
    ["/debug", { page: "debug" }],
  ])("parses %s", (path, expected) => {
    expect(parseAppPath(path)).toEqual(expected);
  });

  it("encodes camera IDs when building a path and decodes them when parsing", () => {
    const route = { page: "field", view: "camera", cameraId: "北側 camera 1" } as const;
    const path = appRoutePath(route);

    expect(path).toBe("/field/camera/%E5%8C%97%E5%81%B4%20camera%201");
    expect(parseAppPath(path)).toEqual(route);
  });

  it.each(["/", "/unknown", "/field/camera/", "/field/camera/%E0%A4%A"])(
    "falls back to the map for an unsupported path: %s",
    (path) => expect(parseAppPath(path)).toEqual(fieldMapRoute),
  );

  it("maps routes to the four navigation targets", () => {
    expect(navigationTargetForRoute(fieldMapRoute)).toBe("map");
    expect(navigationTargetForRoute({
      page: "field", view: "camera", cameraId: "camera_2",
    })).toBe("field");
    expect(navigationTargetForRoute({ page: "settings" })).toBe("settings");
    expect(navigationTargetForRoute({ page: "debug" })).toBe("debug");
  });

  it("opens the selected camera from the field navigation", () => {
    expect(routeForNavigationTarget("field", "camera_2")).toEqual({
      page: "field", view: "camera", cameraId: "camera_2",
    });
    expect(routeForNavigationTarget("map", "camera_2")).toEqual(fieldMapRoute);
    expect(routeForNavigationTarget("settings", "camera_2")).toEqual({ page: "settings" });
  });

  it("falls back to the map when no field camera is available", () => {
    expect(routeForNavigationTarget("field", "")).toEqual(fieldMapRoute);
  });
});
