import { describe, expect, it } from "vitest";
import { createPalletPair, validFixedPalletLayout } from "./palletLayout";
import type { CameraSettings, PalletSettings } from "./types";

const camera: CameraSettings = {
  camera_id: "camera_1", display_name: "カメラ1", driver: "orbbec_network",
  camera_code: "CAM-001", manufacturer: null, model_name: null,
  camera_service_url: "http://camera-1:8001",
  serial_number: null, location_id: 1,
  factory_name: null, building_name: null, floor_name: null,
  area_name: null, mounting_note: null,
  ip: "192.168.253.100", port: 9000, width: 512, height: 512,
  depth_width: 512, depth_height: 512, fps: 15, align_depth_to_color: false,
};
const pallets: PalletSettings[] = [1, 2].map((palletNumber): PalletSettings => ({
  pallet_id: palletNumber,
  pallet_number: palletNumber,
  camera_id: "camera_1",
  display_name: `パレット ${palletNumber}`,
  enabled: palletNumber === 1,
  low_stock_threshold_liters: 5,
  email_rearm_margin_liters: 154,
  plane_roi: palletNumber === 1 ? [0.05, 0.15, 0.48, 0.95] : [0.52, 0.15, 0.95, 0.95],
  single_box_labels: ["cardboard_box"],
  mixed_box_groups: [],
  reference_box_label: "cardboard_box",
}));

describe("fixed two-pallet layout", () => {
  it("creates two disabled slots for a new camera once", () => {
    const added = createPalletPair("camera_2", pallets);
    expect(added.map((pallet) => pallet.pallet_number)).toEqual([1, 2]);
    expect(added.map((pallet) => pallet.pallet_id)).toEqual([3, 4]);
    expect(added.every((pallet) => !pallet.enabled)).toBe(true);
  });

  it("requires pallet 1 and 2 for every camera", () => {
    const second = { ...camera, camera_id: "camera_2", camera_code: "CAM-002",
      location_id: 2, port: 9001 };
    const added = createPalletPair("camera_2", pallets);
    expect(validFixedPalletLayout([camera, second], [...pallets, ...added])).toBe(true);
    expect(validFixedPalletLayout([camera, second], [...pallets, added[0]])).toBe(false);
  });
});
