import type { DashboardState } from "./types";

export function effectiveDashboardState({ monitorRunning, cameraConnected, measurementState,
  measurementMessage }: {
  monitorRunning: boolean;
  cameraConnected: boolean;
  measurementState: DashboardState;
  measurementMessage: string;
}): { state: DashboardState; message: string } {
  if (!monitorRunning) return { state: "unavailable", message: "監視停止中" };
  if (!cameraConnected) return { state: "unavailable", message: "カメラ切断" };
  return { state: measurementState, message: measurementMessage };
}
