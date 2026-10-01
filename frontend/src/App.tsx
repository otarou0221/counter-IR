import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useCameraController } from "./controllers/useCameraController";
import { useDashboardController } from "./controllers/useDashboardController";
import { useMonitorController } from "./controllers/useMonitorController";
import { useSettingsController } from "./controllers/useSettingsController";
import type { RunOperation } from "./controllers/types";
import Navigation from "./Navigation";
import {
  fieldMapRoute,
  navigationTargetForRoute,
  routeForNavigationTarget,
  type NavigationTarget,
} from "./routes";
import SystemStatusBar from "./SystemStatusBar";
import type { OperationalIssue } from "./types";
import type { NoticeHandler, UiNotice } from "./uiNotice";
import { useAppRouter } from "./useAppRouter";
import { useUnsavedChangesWarning } from "./useUnsavedChangesWarning";

const DebugPage = lazy(() => import("./DebugPage"));
const FieldPage = lazy(() => import("./FieldPage"));
const SettingsPage = lazy(() => import("./SettingsPage"));

export default function App() {
  const { route, navigate } = useAppRouter();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<UiNotice>({
    message: "設定を読み込み中です",
    tone: "info",
  });

  const announce = useCallback<NoticeHandler>((message, tone = "info") => {
    setNotice({ message, tone });
  }, []);
  const runOperation = useCallback<RunOperation>(async (action) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      announce(error instanceof Error ? error.message : String(error), "error");
    } finally {
      setBusy(false);
    }
  }, [announce]);

  const monitor = useMonitorController({ announce, runOperation });
  const dashboard = useDashboardController(route.page === "field" && route.view === "map");
  const camera = useCameraController({
    cameraStreams: monitor.cameraStreams,
    announce,
  });
  const settings = useSettingsController({
    selectedCameraId: camera.selectedCameraId,
    onCameraChange: camera.selectCamera,
    monitorRunning: monitor.monitor.running,
    announce,
    runOperation,
    clearCalibrations: monitor.clearCalibrations,
    markCalibrated: monitor.markCalibrated,
  });
  useUnsavedChangesWarning(settings.configDirty);
  const cameraViewOpen = route.page === "field" && route.view === "camera";

  useEffect(() => {
    if (!cameraViewOpen) camera.stopLiveStream();
  }, [camera.stopLiveStream, cameraViewOpen]);

  useEffect(() => {
    if (!settings.config || route.page !== "field" || route.view !== "camera") return;
    if (settings.config.cameras.some((item) => item.camera_id === route.cameraId)) {
      camera.selectCamera(route.cameraId);
      return;
    }
    camera.selectCamera(settings.config.cameras[0]?.camera_id ?? "");
    navigate(fieldMapRoute, { replace: true });
    announce(`指定されたカメラが見つからないため、工場マップを表示しました: ${route.cameraId}`, "warning");
  }, [announce, camera.selectCamera, navigate, route, settings.config]);

  const openFieldCamera = (cameraId: string) => {
    camera.openCamera(cameraId);
    navigate({ page: "field", view: "camera", cameraId });
  };

  const openNavigationTarget = (target: NavigationTarget) => {
    const nextRoute = routeForNavigationTarget(target, camera.selectedCameraId);
    if (target === "field" && nextRoute.page === "field" && nextRoute.view === "map") {
      announce("現場用画面を開くカメラが登録されていません", "warning");
    }
    navigate(nextRoute);
  };

  const openIssueAction = (issue: OperationalIssue) => {
    if (issue.camera_id) camera.selectCamera(issue.camera_id);
    if (issue.action_target === "field_camera" && issue.camera_id) {
      openFieldCamera(issue.camera_id);
    } else if (issue.action_target === "settings") {
      navigate({ page: "settings" });
    } else if (issue.action_target === "debug") {
      navigate({ page: "debug" });
    }
  };

  return <main>
    <Navigation target={navigationTargetForRoute(route)} onChange={openNavigationTarget} />
    <SystemStatusBar busy={busy} dirty={settings.configDirty}
      startDisabled={!settings.config || !settings.configValid}
      monitor={monitor.monitor} notice={notice}
      onStart={monitor.startMonitor} onStop={monitor.stopMonitor}
      onIssueAction={openIssueAction} />
    <Suspense fallback={<div className="page-loading">画面を読み込み中です</div>}>
      {route.page === "field" && <FieldPage view={route.view} busy={busy}
        dirty={settings.configDirty}
        cameraConfigs={settings.config?.cameras ?? []}
        pallets={settings.config?.pallets ?? []}
        cameras={monitor.cameraStreams} selectedCameraId={camera.selectedCameraId}
        onOpenMap={() => navigate(fieldMapRoute)} onOpenCamera={openFieldCamera}
        result={monitor.result} dashboard={dashboard.dashboard}
        dashboardStatus={dashboard.status} dashboardError={dashboard.error}
        showLive={camera.showLiveStream} revision={camera.streamRevision}
        onShow={camera.showLiveStreamNow} onHide={camera.hideLiveStream}
        onRefreshDashboard={dashboard.refresh} onRetryDashboard={dashboard.retry}
        onMessage={announce} />}
      {route.page === "debug" && <DebugPage
        systemBusy={busy} monitoring={monitor.monitor.running} dirty={settings.configDirty}
        config={settings.config} selectedCameraId={camera.selectedCameraId}
        onCameraChange={camera.selectCamera} onMessage={announce} />}
      {route.page === "settings" && <SettingsPage busy={busy}
        monitoring={monitor.monitor.running} dirty={settings.configDirty}
        valid={settings.configValid} validationMessage={settings.validationMessage}
        validationIssues={settings.validationIssues}
        config={settings.config} savedConfig={settings.savedConfig}
        cameras={monitor.cameraStreams}
        selectedCameraId={camera.selectedCameraId}
        roiReferences={settings.roiReferences}
        floorCaptures={settings.floorCaptures}
        floorCaptureLimit={settings.floorCaptureLimit}
        calibratedCameraIds={monitor.calibratedCameraIds}
        onCameraChange={camera.selectCamera}
        onSave={settings.save} onSaveRois={settings.saveRois}
        onRetryCalibration={settings.retryCalibration}
        onCaptureRoiImage={settings.captureRoiImage}
        onSelectFloorCapture={settings.selectFloorCapture}
        onMessage={announce} onConfigChange={settings.updateConfig}
        onRoiChange={settings.updateRoi}
        onEnabledChange={settings.updatePalletEnabled} />}
    </Suspense>
  </main>;
}
