import { ipv4ValidationError } from "./ipv4";
import type { CameraSettings } from "./types";

export type CameraFieldName =
  | "display_name"
  | "camera_code"
  | "ip"
  | "port"
  | "factory_name"
  | "building_name"
  | "floor_name";

export type CameraFieldErrors = Partial<Record<CameraFieldName, string>>;

export function cameraFieldErrors(camera: CameraSettings): CameraFieldErrors {
  const errors: CameraFieldErrors = {};
  if (!camera.display_name.trim()) errors.display_name = "表示名を入力してください";
  if (!camera.camera_code.trim()) errors.camera_code = "カメラ管理コードを入力してください";
  const ipError = ipv4ValidationError(camera.ip);
  if (ipError) errors.ip = ipError;
  if (!Number.isInteger(camera.port) || camera.port < 1 || camera.port > 65535) {
    errors.port = "接続先ポートを1〜65535で入力してください";
  }
  if (!camera.factory_name?.trim()) errors.factory_name = "工場名を入力してください";
  if (!camera.building_name?.trim()) errors.building_name = "建物・工場棟名を入力してください";
  if (!camera.floor_name?.trim()) errors.floor_name = "フロア名を入力してください";
  return errors;
}

export function validCameraConfiguration(cameras: CameraSettings[]): boolean {
  if (cameras.length === 0) return false;
  const ids = new Set<string>();
  const endpoints = new Set<string>();
  const cameraCodes = new Set<string>();
  const locationIds = new Set<number>();
  const serialNumbers = new Set<string>();
  for (const camera of cameras) {
    if (Object.keys(cameraFieldErrors(camera)).length > 0
      || !camera.camera_id.trim()
      || !camera.driver.trim() || !camera.camera_service_url.trim()
      || !Number.isInteger(camera.width) || camera.width < 1
      || !Number.isInteger(camera.height) || camera.height < 1
      || !Number.isInteger(camera.depth_width) || camera.depth_width < 1
      || !Number.isInteger(camera.depth_height) || camera.depth_height < 1
      || camera.width !== camera.depth_width || camera.height !== camera.depth_height
      || camera.align_depth_to_color !== false
      || !Number.isInteger(camera.fps) || camera.fps < 1 || camera.fps > 60) return false;
    const id = camera.camera_id.toLocaleLowerCase();
    const endpoint = `${camera.driver.toLocaleLowerCase()}:${camera.ip.trim().toLocaleLowerCase()}:${camera.port}`;
    const cameraCode = camera.camera_code.trim().toLocaleLowerCase();
    const locationId = camera.location_id;
    const serialNumber = camera.serial_number?.trim().toLocaleLowerCase();
    if (ids.has(id) || endpoints.has(endpoint) || cameraCodes.has(cameraCode)
      || (locationId !== null && locationIds.has(locationId))
      || (serialNumber && serialNumbers.has(serialNumber))) return false;
    ids.add(id);
    endpoints.add(endpoint);
    cameraCodes.add(cameraCode);
    if (locationId !== null) locationIds.add(locationId);
    if (serialNumber) serialNumbers.add(serialNumber);
  }
  return true;
}
