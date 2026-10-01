import { effectiveDashboardState } from "../dashboardState";
import type {
  CameraStreamStatus,
  DashboardCameraState,
  DashboardState,
} from "../types";

export type CameraListPallet = {
  palletSlotId: number;
  palletNumber: number;
  displayName: string;
  state: DashboardState;
  message: string;
  inventoryCount: number | null;
  volumeLiters: number | null;
  measuredAt: string | null;
};

export type CameraListItem = {
  cameraId: string;
  displayName: string;
  location: string;
  connected: boolean;
  state: DashboardState;
  lastMeasuredAt: string | null;
  pallets: CameraListPallet[];
};

const statePriority: Record<DashboardState, number> = {
  normal: 0,
  low_stock: 1,
  unavailable: 2,
};

function cameraLocation(camera: DashboardCameraState): string {
  return [camera.factory_name, camera.building_name, camera.floor_name, camera.area_name]
    .filter(Boolean).join(" / ") || "場所未設定";
}

export function buildCameraList(
  cameras: DashboardCameraState[],
  streams: CameraStreamStatus[],
  monitorRunning: boolean,
): CameraListItem[] {
  const connectedByCameraId = new Map(streams.map((stream) => [
    stream.camera?.camera_id,
    stream.connected,
  ]));
  return cameras.map((camera) => {
    const connected = connectedByCameraId.get(camera.camera_id) ?? false;
    const pallets = camera.pallets.map((pallet) => {
      const cameraUnavailable = camera.state === "unavailable";
      const effective = effectiveDashboardState({
        monitorRunning,
        cameraConnected: connected,
        measurementState: cameraUnavailable ? "unavailable" : pallet.state,
        measurementMessage: cameraUnavailable
          ? camera.state_message
          : pallet.state === "low_stock" ? "低在庫" : "正常",
      });
      return {
        palletSlotId: pallet.pallet_slot_id,
        palletNumber: pallet.pallet_number,
        displayName: pallet.display_name,
        state: effective.state,
        message: effective.message,
        inventoryCount: pallet.inventory_count,
        volumeLiters: pallet.volume_liters,
        measuredAt: pallet.measured_at,
      };
    });
    const state = pallets.reduce<DashboardState>((worst, pallet) => (
      statePriority[pallet.state] > statePriority[worst] ? pallet.state : worst
    ), "normal");
    return {
      cameraId: camera.camera_id,
      displayName: camera.display_name,
      location: cameraLocation(camera),
      connected,
      state: pallets.length ? state : "unavailable",
      lastMeasuredAt: camera.last_success_at,
      pallets,
    };
  });
}
