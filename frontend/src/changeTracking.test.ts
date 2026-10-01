import { describe, expect, it } from "vitest";
import {
  fieldChanged,
  hasUnsavedChanges,
  structuredValueChanged,
  valuesEqual,
} from "./changeTracking";

describe("change tracking", () => {
  it("compares one field against the saved object", () => {
    const current = { name: "カメラ1", port: 8090 };
    expect(fieldChanged(current, { ...current }, "port")).toBe(false);
    expect(fieldChanged(current, { ...current, port: 8091 }, "port")).toBe(true);
    expect(fieldChanged(current, undefined, "port")).toBe(true);
  });

  it("compares array based settings by value", () => {
    expect(structuredValueChanged([["A", "B"]], [["A", "B"]])).toBe(false);
    expect(structuredValueChanged([["A", "B"]], [["B", "A"]])).toBe(true);
  });

  it("treats text and checkbox values restored to the saved state as unchanged", () => {
    const saved = { display_name: "カメラ1", enabled: true };
    expect(hasUnsavedChanges({ ...saved, display_name: "変更中" }, saved)).toBe(true);
    expect(hasUnsavedChanges({ ...saved, display_name: "カメラ1" }, saved)).toBe(false);
    expect(hasUnsavedChanges({ ...saved, enabled: false }, saved)).toBe(true);
    expect(hasUnsavedChanges({ ...saved, enabled: true }, saved)).toBe(false);
    expect(hasUnsavedChanges(null, saved)).toBe(false);
    expect(hasUnsavedChanges(saved, null)).toBe(true);
  });

  it("compares nested settings without depending on object key order", () => {
    const saved = {
      cameras: [{ camera_id: "camera_1", port: 8090 }],
      pallets: [{ pallet_id: 1, enabled: true, groups: [["A", "B"]] }],
    };
    const reordered = {
      pallets: [{ groups: [["A", "B"]], enabled: true, pallet_id: 1 }],
      cameras: [{ port: 8090, camera_id: "camera_1" }],
    };
    expect(valuesEqual(reordered, saved)).toBe(true);
    expect(valuesEqual({ ...reordered, cameras: [{ ...reordered.cameras[0], port: 8091 }] }, saved))
      .toBe(false);
  });

  it("does not confuse invalid numbers or missing fields with saved values", () => {
    expect(valuesEqual({ frame_count: Number.NaN }, { frame_count: null })).toBe(false);
    expect(valuesEqual({ frame_count: Number.NaN }, { frame_count: Number.NaN })).toBe(true);
    expect(valuesEqual({ enabled: true, note: undefined }, { enabled: true })).toBe(false);
  });
});
