import { describe, expect, it } from "vitest";
import { createCameraSettings, nextCameraId } from "./cameraSettings";
import { cameraFieldErrors, validCameraConfiguration } from "./cameraValidation";
import type { CameraSettings } from "./types";

const camera: CameraSettings = {
  camera_id: "camera_1", display_name: "カメラ1", driver: "orbbec_network",
  camera_code: "CAM-001", manufacturer: null, model_name: null,
  camera_service_url: "http://camera-1:8001",
  serial_number: null, location_id: 1,
  factory_name: "長岡工場", building_name: "第5工場", floor_name: "3階",
  area_name: "資材エリア", mounting_note: null,
  ip: "192.168.253.7", port: 8090, width: 512, height: 512,
  depth_width: 512, depth_height: 512, fps: 15, align_depth_to_color: false,
};

describe("camera settings", () => {
  it("creates a new stable id with an explicit empty connection destination", () => {
    const added = createCameraSettings([camera]);
    expect(added.camera_id).toBe("camera_2");
    expect(added.ip).toBe("");
    expect(added.port).toBe(0);
    expect(added.camera_service_url).toBe("http://camera-2:8001");
    expect(added.width).toBe(camera.width);
    expect(camera.ip).toBe("192.168.253.7");
  });

  it("fills an id gap instead of depending on the render order", () => {
    expect(nextCameraId([camera, { ...camera, camera_id: "camera_3" }])).toBe("camera_2");
  });

  it("requires an explicit destination before saving", () => {
    const added = createCameraSettings([camera]);
    expect(cameraFieldErrors(added).ip).toBe("接続先IPを入力してください");
    expect(validCameraConfiguration([camera, added])).toBe(false);
  });

  it("rejects malformed and out-of-range IPv4 addresses", () => {
    expect(cameraFieldErrors({ ...camera, ip: "camera.local" }).ip)
      .toBe("IPv4アドレスを4つの数字で入力してください");
    expect(cameraFieldErrors({ ...camera, ip: "192.168.1.256" }).ip)
      .toBe("各数字を0〜255で入力してください");
    expect(validCameraConfiguration([{ ...camera, ip: "192.168.1" }])).toBe(false);
  });

  it("requires factory, building and floor names but keeps area optional", () => {
    expect(validCameraConfiguration([{ ...camera, manufacturer: null, model_name: null }])).toBe(true);
    expect(cameraFieldErrors({ ...camera, factory_name: null }).factory_name)
      .toBe("工場名を入力してください");
    expect(cameraFieldErrors({ ...camera, building_name: "" }).building_name)
      .toBe("建物・工場棟名を入力してください");
    expect(cameraFieldErrors({ ...camera, floor_name: "" }).floor_name)
      .toBe("フロア名を入力してください");
    expect(validCameraConfiguration([{ ...camera, area_name: null }])).toBe(true);
  });

  it("allows one NAPT address with different published ports", () => {
    const first = { ...camera, ip: "192.168.253.100", port: 9000 };
    const second = createCameraSettings([camera]);
    second.ip = "192.168.253.100";
    second.port = 9001;
    second.factory_name = "第5工場";
    second.building_name = "第5工場";
    second.floor_name = "3階";
    second.area_name = "資材エリア2";
    expect(validCameraConfiguration([first, second])).toBe(true);
  });

  it("rejects duplicate connection destinations", () => {
    const duplicate = { ...camera, camera_id: "camera_2" };
    expect(validCameraConfiguration([camera, duplicate])).toBe(false);
  });
});
