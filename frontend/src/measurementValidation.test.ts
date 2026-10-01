import { describe, expect, it } from "vitest";
import { measurementFieldErrors } from "./measurementValidation";
import type { SystemSettings } from "./types";

const settings = {
  monitor_interval_seconds: 600,
  pallet_height_mm: 150,
  frame_count: 30,
  measurement_frame_count: 1,
  measurement_concurrency: 3,
  warmup_frames: 5,
  grid_mm: 10,
  occupied_height_mm: 30,
} as SystemSettings;

describe("measurement settings validation", () => {
  it("uses ten minutes as a valid initial interval", () => {
    expect(measurementFieldErrors(settings)).toEqual({});
  });

  it("rejects blanks, fractional minutes and out-of-range values", () => {
    expect(measurementFieldErrors({ ...settings, monitor_interval_seconds: Number.NaN })
      .monitor_interval_seconds).toBeDefined();
    expect(measurementFieldErrors({ ...settings, monitor_interval_seconds: 90 })
      .monitor_interval_seconds).toBeDefined();
    expect(measurementFieldErrors({ ...settings, frame_count: 2 }).frame_count)
      .toBeDefined();
  });
});
