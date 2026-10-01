import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { buildCalibrationPlan } from "../calibrationPlan";
import { hasUnsavedChanges } from "../changeTracking";
import type { NormalizedRoi } from "../roi";
import { settingsValidationDetails } from "../settingsValidation";
import type {
  CameraCalibrationResponse,
  RoiReferenceCapture,
  RoiReferenceCatalog,
  RoiReferenceChange,
  SavedCapture,
  SystemSettings,
} from "../types";
import type { NoticeHandler } from "../uiNotice";
import type { RunOperation } from "./types";

type Props = {
  selectedCameraId: string;
  onCameraChange: (cameraId: string) => void;
  monitorRunning: boolean;
  announce: NoticeHandler;
  runOperation: RunOperation;
  clearCalibrations: (cameraIds: string[]) => void;
  markCalibrated: (cameraId: string) => void;
};

export function useSettingsController({ selectedCameraId, onCameraChange, monitorRunning,
  announce, runOperation, clearCalibrations, markCalibrated }: Props) {
  const [config, setConfig] = useState<SystemSettings | null>(null);
  const [savedConfig, setSavedConfig] = useState<SystemSettings | null>(null);
  const [roiReferences, setRoiReferences] = useState<RoiReferenceCapture[]>([]);
  const [floorCaptures, setFloorCaptures] = useState<SavedCapture[]>([]);
  const [floorCaptureLimit, setFloorCaptureLimit] = useState(5);
  const configDirty = useMemo(
    () => hasUnsavedChanges(config, savedConfig),
    [config, savedConfig],
  );
  const validationIssues = useMemo(
    () => config ? settingsValidationDetails(config) : [],
    [config],
  );
  const configValid = config !== null && validationIssues.length === 0;
  const validationMessage = validationIssues[0]?.message;

  const refreshRoiReferences = useCallback(() => api<RoiReferenceCatalog>("/api/roi-references")
    .then((catalog) => {
      setRoiReferences(catalog.captures);
      setFloorCaptures(catalog.floor_captures);
      setFloorCaptureLimit(catalog.floor_capture_limit);
      return catalog;
    }), []);

  useEffect(() => {
    api<SystemSettings>("/api/config")
      .then((loaded) => {
        setConfig(loaded);
        setSavedConfig(loaded);
        onCameraChange(loaded.cameras[0]?.camera_id ?? "");
        announce("床基準ROIをパレット高さ分だけ持ち上げる方式で動作します");
      })
      .catch((error: Error) => announce(error.message, "error"));
    refreshRoiReferences().catch((error: Error) => announce(error.message, "error"));
  }, [announce, onCameraChange, refreshRoiReferences]);

  const applySavedConfig = (saved: SystemSettings) => {
    setConfig(saved);
    setSavedConfig(saved);
    onCameraChange(saved.cameras.some((camera) => camera.camera_id === selectedCameraId)
      ? selectedCameraId : saved.cameras[0]?.camera_id ?? "");
  };

  const persistConfig = async (candidate: SystemSettings) => {
    const saved = await api<SystemSettings>("/api/config", {
      method: "PUT", body: JSON.stringify(candidate),
    });
    applySavedConfig(saved);
    const references = await refreshRoiReferences();
    return { saved, references };
  };

  const requestCameraCalibration = (cameraId: string) => api<CameraCalibrationResponse>(
    `/api/cameras/${encodeURIComponent(cameraId)}/calibration`,
    { method: "POST" },
  );

  const calibrateCameras = async (cameraIds: string[]) => {
    clearCalibrations(cameraIds);
    const completed: string[] = [];
    for (const cameraId of cameraIds) {
      announce(`${cameraId}の床基準校正を実行中です`);
      const response = await requestCameraCalibration(cameraId);
      completed.push(response.camera_id);
      markCalibrated(response.camera_id);
    }
    return completed;
  };

  const save = () => runOperation(async () => {
    if (!config || !configValid) throw new Error("未入力・重複・選択内容を修正してください");
    announce("設定を保存しています");
    const { saved, references } = await persistConfig(config);
    if (monitorRunning) {
      announce("警告体積とメール再有効化増加量を保存しました。次回測定から反映します", "success");
      return;
    }
    const plan = buildCalibrationPlan(saved, references.captures);
    try {
      await calibrateCameras(plan.readyCameraIds);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`設定は保存しましたが、床基準校正に失敗しました: ${detail}`);
    }
    if (!plan.readyCameraIds.length) {
      announce(
        `設定を保存しました。床画像未選択のため校正できません: ${plan.missingReferenceCameraIds.join(", ")}`,
        "warning",
      );
    } else if (plan.missingReferenceCameraIds.length) {
      announce(
        `設定を保存し、床画像があるカメラを校正しました。画像未選択: ${plan.missingReferenceCameraIds.join(", ")}`,
        "warning",
      );
    } else {
      announce(`設定保存と床基準校正が完了しました: ${plan.readyCameraIds.join(", ")}`, "success");
    }
  });

  const saveRois = () => runOperation(async () => {
    if (!config) throw new Error("設定の読み込み完了後に保存してください");
    if (!selectedCameraId) throw new Error("校正するカメラを選択してください");
    announce("ROI設定を保存しています");
    await persistConfig(config);
    announce(`${selectedCameraId}のROIを保存し、床基準校正を実行中です`);
    try {
      await calibrateCameras([selectedCameraId]);
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`ROI設定は保存しましたが、床基準校正に失敗しました: ${detail}`);
    }
    announce(`ROI設定と床基準校正を保存しました: ${selectedCameraId}`, "success");
  });

  const updateConfig = (updated: SystemSettings) => {
    setConfig(updated);
    onCameraChange(updated.cameras.some((camera) => camera.camera_id === selectedCameraId)
      ? selectedCameraId : updated.cameras[0]?.camera_id ?? "");
  };

  const updateRoi = (palletId: number, roi: NormalizedRoi) => {
    if (!config || !configValid) return;
    updateConfig({
      ...config,
      pallets: config.pallets.map((pallet) => (
        pallet.pallet_id === palletId ? { ...pallet, plane_roi: roi } : pallet
      )),
    });
  };

  const updatePalletEnabled = (palletId: number, enabled: boolean) => {
    if (!config || !configValid) return;
    if (!enabled && config.pallets.filter((pallet) => pallet.enabled).length === 1) {
      announce("少なくとも1つのパレットを有効にしてください", "warning");
      return;
    }
    updateConfig({
      ...config,
      pallets: config.pallets.map((pallet) => (
        pallet.pallet_id === palletId ? { ...pallet, enabled } : pallet
      )),
    });
    announce(`パレット${palletId}を${enabled ? "有効" : "無効"}にしました。保存してください`, "warning");
  };

  const retryCalibration = () => runOperation(async () => {
    if (!selectedCameraId) throw new Error("校正するカメラを選択してください");
    announce(`${selectedCameraId}の床基準校正を再試行中です`);
    const response = await requestCameraCalibration(selectedCameraId);
    markCalibrated(response.camera_id);
    announce(`床基準校正が完了しました: ${response.camera_id}`, "success");
  });

  const savePendingConfigForRoiAction = async (actionMessage: string) => {
    if (!config) throw new Error("設定の読み込み完了後に操作してください");
    if (!configValid) throw new Error("未入力・重複・選択内容を修正してください");
    if (!configDirty) return;
    announce(actionMessage);
    const saved = await api<SystemSettings>("/api/config", {
      method: "PUT", body: JSON.stringify(config),
    });
    applySavedConfig(saved);
    await refreshRoiReferences();
  };

  const captureRoiImage = () => runOperation(async () => {
    await savePendingConfigForRoiAction("未保存設定を反映してからROI画像を撮影します");
    announce("パレットを置いていない床を撮影し、ROI選択画像を保存中です");
    const changed = await api<RoiReferenceChange>("/api/roi-references/capture", {
      method: "POST",
      body: JSON.stringify({ camera_id: selectedCameraId }),
    });
    await refreshRoiReferences();
    const cleanup = changed.removed_capture_ids.length
      ? ` 古い床撮影${changed.removed_capture_ids.length}件を整理しました。` : "";
    announce(`床画像を保存しました。画像上をドラッグしてROIを設定してください。${cleanup}`, "success");
  });

  const selectFloorCapture = (captureId: string) => runOperation(async () => {
    await savePendingConfigForRoiAction("未保存設定を反映してから床撮影を選択します");
    const changed = await api<RoiReferenceChange>("/api/roi-references/select-floor", {
      method: "POST",
      body: JSON.stringify({ camera_id: selectedCameraId, capture_id: captureId }),
    });
    await refreshRoiReferences();
    const cleanup = changed.removed_capture_ids.length
      ? ` 古い撮影${changed.removed_capture_ids.length}件を整理しました。` : "";
    announce(`保存済み床撮影を選択しました。画像上でROIを確認してください。${cleanup}`, "success");
  });

  return {
    config,
    savedConfig,
    configDirty,
    configValid,
    validationMessage,
    validationIssues,
    roiReferences,
    floorCaptures,
    floorCaptureLimit,
    save,
    saveRois,
    retryCalibration,
    captureRoiImage,
    selectFloorCapture,
    updateConfig,
    updateRoi,
    updatePalletEnabled,
  };
}
