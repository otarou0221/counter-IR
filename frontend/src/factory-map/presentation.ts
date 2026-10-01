import { effectiveDashboardState } from "../dashboardState";
import type {
  CameraStreamStatus,
  DashboardCameraState,
  DashboardPalletState,
  DashboardState,
} from "../types";

export type PalletMarker = {
  camera: DashboardCameraState;
  pallet: DashboardPalletState;
};

export const stateColors: Record<DashboardState, string> = {
  normal: "#168a45",
  low_stock: "#d92d20",
  unavailable: "#6b7280",
};

export function palletMarkers(cameras: DashboardCameraState[]): PalletMarker[] {
  return cameras.flatMap((camera) => camera.pallets.map((pallet) => ({
    camera,
    pallet,
  })));
}

export function markerLabel(
  camera: DashboardCameraState,
  pallet: DashboardPalletState,
): string {
  const numeric = camera.camera_id.match(/(\d+)$/)?.[1];
  return `${numeric ?? camera.camera_code.slice(-3)}-${pallet.pallet_number}`;
}

export function effectivePalletState(
  camera: DashboardCameraState,
  pallet: DashboardPalletState,
  streams: CameraStreamStatus[],
  monitorRunning: boolean,
): { state: DashboardState; message: string } {
  const stream = streams.find((item) => item.camera?.camera_id === camera.camera_id);
  const cameraUnavailable = camera.state === "unavailable";
  return effectiveDashboardState({
    monitorRunning,
    cameraConnected: Boolean(stream?.connected),
    measurementState: cameraUnavailable ? "unavailable" : pallet.state,
    measurementMessage: cameraUnavailable
      ? camera.state_message
      : pallet.state === "low_stock" ? "低在庫" : "正常",
  });
}

export function tooltipText(
  camera: DashboardCameraState,
  pallet: DashboardPalletState,
  message: string,
): string {
  const count = pallet.inventory_count === null ? "未測定" : `${pallet.inventory_count}箱`;
  const volume = pallet.volume_liters === null
    ? ""
    : `\n残体積 ${pallet.volume_liters.toFixed(1)}L`;
  return `${camera.display_name} / P${pallet.pallet_number}\n${message}\n${count}${volume}`;
}
