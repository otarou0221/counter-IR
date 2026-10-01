import { describe, expect, it } from "vitest";
import { buildCameraList } from "./cameraList";
import type { CameraStreamStatus, DashboardCameraState } from "../types";

const camera = {
  camera_id: "camera_1",
  display_name: "入口カメラ",
  factory_name: "第一工場",
  building_name: "A棟",
  floor_name: "1F",
  area_name: null,
  state: "normal",
  state_message: "正常",
  pallets: [{
    pallet_slot_id: 10,
    pallet_number: 1,
    display_name: "P1",
    state: "low_stock",
    inventory_count: 2,
    volume_liters: 12.3,
    measured_at: "2026-09-02T00:00:00Z",
  }],
} as DashboardCameraState;

const connectedStream = {
  connected: true,
  camera: { camera_id: "camera_1" },
} as CameraStreamStatus;

describe("buildCameraList", () => {
  it("builds an operational list without changing the source data", () => {
    const result = buildCameraList([camera], [connectedStream], true);

    expect(result[0]).toMatchObject({
      cameraId: "camera_1",
      displayName: "入口カメラ",
      location: "第一工場 / A棟 / 1F",
      connected: true,
      state: "low_stock",
    });
    expect(result[0].pallets[0]).toMatchObject({ state: "low_stock", message: "低在庫" });
    expect(camera.pallets[0].state).toBe("low_stock");
  });

  it("prioritizes monitoring and connection state", () => {
    expect(buildCameraList([camera], [connectedStream], false)[0].pallets[0].message)
      .toBe("監視停止中");
    expect(buildCameraList([camera], [], true)[0]).toMatchObject({
      connected: false,
      state: "unavailable",
    });
  });
});
