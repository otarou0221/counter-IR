import { describe, expect, it } from "vitest";
import { createBoxClassSpec, renamePalletBoxLabel } from "./boxCatalog";
import { validBoxConfiguration } from "./boxValidation";
import type { BoxClassSpec, PalletSettings } from "./types";

const catalog: BoxClassSpec[] = [
  { label: "standard", width_mm: 570, depth_mm: 410, height_mm: 335 },
];
const pallet: PalletSettings = {
  pallet_id: 1, pallet_number: 1, camera_id: "camera_1", enabled: true,
  display_name: "パレット 1",
  low_stock_threshold_liters: 5,
  email_rearm_margin_liters: 154,
  plane_roi: [0, 0, .4, .4],
  single_box_labels: ["standard"], mixed_box_groups: [], reference_box_label: "standard",
};

describe("box catalog", () => {
  it("creates an unconfigured box with a unique label", () => {
    expect(createBoxClassSpec([...catalog, { ...catalog[0], label: "box_2" }]))
      .toEqual({ label: "box_3", width_mm: 0, depth_mm: 0, height_mm: 0 });
  });

  it("renames pallet selection and reference together", () => {
    const renamed = renamePalletBoxLabel([
      { ...pallet, mixed_box_groups: [["standard", "small"]] },
    ], "standard", "kimwipe_box");
    expect(renamed[0].single_box_labels).toEqual(["kimwipe_box"]);
    expect(renamed[0].mixed_box_groups).toEqual([["kimwipe_box", "small"]]);
    expect(renamed[0].reference_box_label).toBe("kimwipe_box");
  });

  it("rejects box classes until dimensions are entered", () => {
    expect(validBoxConfiguration(catalog, [pallet])).toBe(true);
    expect(validBoxConfiguration([...catalog, { label: "new", width_mm: 0, depth_mm: 0, height_mm: 0 }], [pallet])).toBe(false);
  });

  it("rejects duplicate box names", () => {
    expect(validBoxConfiguration([...catalog, { ...catalog[0], label: "STANDARD" }], [pallet]))
      .toBe(false);
  });
});
