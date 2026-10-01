import { describe, expect, it } from "vitest";
import { settingsFieldId } from "./settingsFieldIds";
import { settingsValidationDetails } from "./settingsValidation";
import type { CameraSettings, PalletSettings, SystemSettings } from "./types";

const camera: CameraSettings = {
  camera_id: "camera_1", display_name: "カメラ1", camera_code: "CAM-001",
  driver: "orbbec_network", ip: "192.168.100.50", port: 8090,
  width: 640, height: 480, depth_width: 640, depth_height: 480, fps: 30,
  align_depth_to_color: false, manufacturer: null, model_name: null, serial_number: null,
  location_id: 1, factory_name: "第1工場", building_name: "A棟", floor_name: "1階",
  area_name: null, mounting_note: null, camera_service_url: "http://camera:8001",
};

function pallet(palletId: number, palletNumber: number): PalletSettings {
  return {
    pallet_id: palletId, pallet_number: palletNumber, camera_id: camera.camera_id,
    display_name: `パレット${palletNumber}`, enabled: palletNumber === 1,
    low_stock_threshold_liters: 5, email_rearm_margin_liters: 10,
    plane_roi: [0.1, 0.1, 0.4, 0.4],
    single_box_labels: ["A"], mixed_box_groups: [], reference_box_label: "A",
  };
}

const settings: SystemSettings = {
  method: "pallet_plane_2roi", cameras: [camera],
  box_catalog: [{ label: "A", width_mm: 100, depth_mm: 200, height_mm: 300 }],
  pallets: [pallet(1, 1), pallet(2, 2)], frame_count: 30,
  measurement_frame_count: 1, measurement_concurrency: 3, warmup_frames: 5,
  grid_mm: 10, pallet_height_mm: 150,
  occupied_height_mm: 30, monitor_interval_seconds: 600,
};

describe("structured settings validation", () => {
  it("returns no issue for a valid configuration", () => {
    expect(settingsValidationDetails(settings)).toEqual([]);
  });

  it("links field errors to the responsible camera and input", () => {
    const invalid = {
      ...settings,
      cameras: [{ ...camera, ip: "999.1.1.1" }],
    };
    expect(settingsValidationDetails(invalid)).toContainEqual({
      key: "camera:camera_1:ip",
      message: "カメラ1: 各数字を0〜255で入力してください",
      targetId: settingsFieldId.camera("camera_1", "ip"),
      cameraId: "camera_1",
    });
  });

  it("returns each invalid measurement field instead of one category error", () => {
    const invalid = { ...settings, frame_count: 2, measurement_frame_count: 0 };
    const issues = settingsValidationDetails(invalid);
    expect(issues.map((issue) => issue.targetId)).toEqual([
      settingsFieldId.measurement("frame_count"),
      settingsFieldId.measurement("measurement_frame_count"),
    ]);
  });
});
