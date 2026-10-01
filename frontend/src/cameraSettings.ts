import type { CameraSettings } from "./types";

export function createCameraSettings(cameras: CameraSettings[]): CameraSettings {
  const template = cameras[0];
  if (!template) throw new Error("複製元のカメラ設定がありません");
  const cameraId = nextCameraId(cameras);
  const cameraNumber = cameras.length + 1;
  return {
    ...template,
    camera_id: cameraId,
    camera_code: `CAM-${String(cameraNumber).padStart(3, "0")}`,
    manufacturer: null,
    model_name: null,
    serial_number: null,
    display_name: `カメラ${cameraNumber}`,
    location_id: null,
    factory_name: null,
    building_name: null,
    floor_name: null,
    area_name: null,
    mounting_note: null,
    camera_service_url: `http://${cameraId.replaceAll("_", "-")}:8001`,
    ip: "",
    port: 0,
  };
}

export function nextCameraId(cameras: CameraSettings[]): string {
  const existing = new Set(cameras.map((camera) => camera.camera_id));
  let index = 1;
  while (existing.has(`camera_${index}`)) index += 1;
  return `camera_${index}`;
}
