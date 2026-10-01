import { useCallback, useState } from "react";
import { api } from "../api";
import type { CameraStreamStatus, Measurement, MonitorStatus, SystemStatus } from "../types";
import type { NoticeHandler } from "../uiNotice";
import { usePolling } from "../usePolling";
import type { RunOperation } from "./types";

const stoppedMonitor: MonitorStatus = {
  running: false,
  stopping: false,
  interval_seconds: 600,
  completed_measurements: 0,
  consecutive_errors: 0,
  last_started_at: null,
  last_finished_at: null,
  last_error: null,
  last_outcome: "not_run",
  last_issues: [],
  email_notifications_enabled: false,
  last_email_sent_at: null,
  last_email_error: null,
  last_email_issue: null,
  last_result: null,
};

export function useMonitorController({ announce, runOperation }: {
  announce: NoticeHandler;
  runOperation: RunOperation;
}) {
  const [monitor, setMonitor] = useState<MonitorStatus>(stoppedMonitor);
  const [cameraStreams, setCameraStreams] = useState<CameraStreamStatus[]>([]);
  const [calibratedCameraIds, setCalibratedCameraIds] = useState<string[]>([]);
  const [result, setResult] = useState<Measurement | null>(null);

  const refreshStatus = useCallback(() => api<SystemStatus>("/api/status")
    .then((status) => {
      setCameraStreams(status.cameras);
      setMonitor(status.monitor);
      setCalibratedCameraIds(status.calibrated_camera_ids);
      if (status.monitor.last_result) setResult(status.monitor.last_result);
    })
    .catch((error: Error) => announce(error.message, "error")), [announce]);
  usePolling(refreshStatus, 2000);

  const startMonitor = () => runOperation(async () => {
    const status = await api<MonitorStatus>("/api/monitor/start", { method: "POST" });
    setMonitor(status);
    const interval = status.interval_seconds >= 60
      ? `${status.interval_seconds / 60}分`
      : `${status.interval_seconds}秒`;
    announce(`常時監視を開始しました（測定後 ${interval}待機）`, "success");
  });

  const stopMonitor = () => runOperation(async () => {
    const status = await api<MonitorStatus>("/api/monitor/stop", { method: "POST" });
    setMonitor(status);
    announce("停止を受け付けました。実行中の測定が終わると停止します");
  });

  const clearCalibrations = useCallback((cameraIds: string[]) => {
    setCalibratedCameraIds((ids) => ids.filter((id) => !cameraIds.includes(id)));
  }, []);

  const markCalibrated = useCallback((cameraId: string) => {
    setCalibratedCameraIds((ids) => [...new Set([...ids, cameraId])]);
  }, []);

  return {
    monitor,
    cameraStreams,
    calibratedCameraIds,
    result,
    startMonitor,
    stopMonitor,
    clearCalibrations,
    markCalibrated,
  };
}
