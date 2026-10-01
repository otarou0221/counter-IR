import { describe, expect, it } from "vitest";
import { effectiveDashboardState } from "./dashboardState";

describe("effectiveDashboardState", () => {
  it("測定エラーを直前の低在庫状態に関係なく確認必要として扱う", () => {
    expect(effectiveDashboardState({
      monitorRunning: true,
      cameraConnected: true,
      measurementState: "unavailable",
      measurementMessage: "測定エラー",
    })).toEqual({ state: "unavailable", message: "測定エラー" });
  });

  it("カメラ切断と監視停止を測定結果より優先する", () => {
    expect(effectiveDashboardState({
      monitorRunning: true,
      cameraConnected: false,
      measurementState: "low_stock",
      measurementMessage: "低在庫",
    }).state).toBe("unavailable");
    expect(effectiveDashboardState({
      monitorRunning: false,
      cameraConnected: true,
      measurementState: "normal",
      measurementMessage: "正常",
    }).message).toBe("監視停止中");
  });
});
