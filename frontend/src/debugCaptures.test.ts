import { describe, expect, it } from "vitest";
import {
  appendDebugCatalogPage,
  currentCaptureLabel,
} from "./debugCaptures";
import type { DebugCatalog, SavedCapture } from "./types";

function capture(captureId: string, retention: SavedCapture["retention"]): SavedCapture {
  return {
    capture_id: captureId,
    camera_id: "camera_1",
    purpose: "current",
    retention,
    captured_at: "2026-09-03T00:00:00+09:00",
    frame_count: 1,
    color_shape: [720, 1280],
    depth_shape: [720, 1280],
    rgb_path: `captures/${captureId}/rgb.jpg`,
  };
}

function catalog(captures: SavedCapture[]): DebugCatalog {
  return {
    camera_id: "camera_1",
    floor_captures: [],
    current_captures: captures,
    current_has_more: false,
    current_capture_limit: 500,
  };
}

describe("debug capture catalog", () => {
  it("distinguishes monitoring and diagnostic captures by retention", () => {
    expect(currentCaptureLabel(capture("monitor", "transient"))).toContain("【通常監視】");
    expect(currentCaptureLabel(capture("debug", "persistent"))).toContain("【診断撮影】");
  });

  it("appends pages without duplicating an existing capture", () => {
    const merged = appendDebugCatalogPage(
      catalog([capture("capture_3", "transient"), capture("capture_2", "transient")]),
      catalog([capture("capture_2", "transient"), capture("capture_1", "persistent")]),
    );

    expect(merged.current_captures.map((item) => item.capture_id)).toEqual([
      "capture_3", "capture_2", "capture_1",
    ]);
  });
});
