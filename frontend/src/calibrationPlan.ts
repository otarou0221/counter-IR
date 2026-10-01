import type { RoiReferenceCapture, SystemSettings } from "./types";

export type CalibrationPlan = {
  readyCameraIds: string[];
  missingReferenceCameraIds: string[];
};

/** 設定保存後に校正できる有効カメラと、空画像待ちのカメラを分ける。 */
export function buildCalibrationPlan(
  settings: SystemSettings,
  references: RoiReferenceCapture[],
): CalibrationPlan {
  const activeCameraIds = new Set(
    settings.pallets.filter((pallet) => pallet.enabled).map((pallet) => pallet.camera_id),
  );
  const referencedCameraIds = new Set(references.map((reference) => reference.camera_id));
  const orderedActiveIds = settings.cameras
    .map((camera) => camera.camera_id)
    .filter((cameraId) => activeCameraIds.has(cameraId));
  return {
    readyCameraIds: orderedActiveIds.filter((cameraId) => referencedCameraIds.has(cameraId)),
    missingReferenceCameraIds: orderedActiveIds.filter((cameraId) => !referencedCameraIds.has(cameraId)),
  };
}
