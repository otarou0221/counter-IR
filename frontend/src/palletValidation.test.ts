import { describe, expect, it } from "vitest";
import { palletFieldErrors } from "./palletValidation";
import type { BoxClassSpec, PalletSettings } from "./types";

const catalog: BoxClassSpec[] = [
  { label: "A", width_mm: 450, depth_mm: 400, height_mm: 240 },
  { label: "B", width_mm: 570, depth_mm: 410, height_mm: 330 },
  { label: "C", width_mm: 520, depth_mm: 330, height_mm: 150 },
];
const pallet: PalletSettings = {
  pallet_id: 1, pallet_number: 1, camera_id: "camera_1", display_name: "パレット1",
  enabled: true, low_stock_threshold_liters: 5, email_rearm_margin_liters: 154,
  plane_roi: [0.1, 0.1, 0.4, 0.8], single_box_labels: ["A"],
  mixed_box_groups: [], reference_box_label: "A",
};

describe("pallet settings validation", () => {
  it("accepts complete pallet settings", () => {
    expect(palletFieldErrors(pallet, catalog)).toEqual({});
  });

  it("rejects zero-liter alert and rearm values", () => {
    expect(palletFieldErrors({ ...pallet, low_stock_threshold_liters: 0 }, catalog)
      .low_stock_threshold_liters).toBeDefined();
    expect(palletFieldErrors({ ...pallet, email_rearm_margin_liters: 0 }, catalog)
      .email_rearm_margin_liters).toBeDefined();
  });

  it("accepts an explicit mixed box group", () => {
    const configured = {
      ...pallet,
      single_box_labels: ["A", "B"],
      mixed_box_groups: [["B", "C"]],
    };
    expect(palletFieldErrors(configured, catalog)).toEqual({});
  });

  it("rejects a mixed group with only one box", () => {
    const invalid = { ...pallet, mixed_box_groups: [["B"]] };
    expect(palletFieldErrors(invalid, catalog).boxes).toBeDefined();
  });
});
