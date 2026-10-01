import { boxFieldErrors, validBoxConfiguration } from "./boxValidation";
import { cameraFieldErrors, validCameraConfiguration } from "./cameraValidation";
import { measurementFieldErrors } from "./measurementValidation";
import { palletFieldErrors } from "./palletValidation";
import { validFixedPalletLayout } from "./palletLayout";
import { settingsFieldId, settingsSectionIds } from "./settingsFieldIds";
import type { SystemSettings } from "./types";

export type SettingsValidationIssue = {
  key: string;
  message: string;
  targetId: string;
  cameraId?: string;
};

export function settingsValidationDetails(settings: SystemSettings): SettingsValidationIssue[] {
  const issues: SettingsValidationIssue[] = [];
  let cameraFieldIssueCount = 0;
  for (const camera of settings.cameras) {
    for (const [field, message] of Object.entries(cameraFieldErrors(camera))) {
      cameraFieldIssueCount += 1;
      issues.push({
        key: `camera:${camera.camera_id}:${field}`,
        message: `${camera.display_name || camera.camera_id}: ${message}`,
        targetId: settingsFieldId.camera(camera.camera_id, field),
        cameraId: camera.camera_id,
      });
    }
  }
  if (!settings.cameras.length) {
    issues.push({
      key: "camera:none",
      message: "カメラを1台以上登録してください",
      targetId: settingsSectionIds.cameras,
    });
  } else if (cameraFieldIssueCount === 0 && !validCameraConfiguration(settings.cameras)) {
    issues.push({
      key: "camera:configuration",
      message: "カメラID、管理コード、接続先または機器情報の重複・不正値を修正してください",
      targetId: settingsSectionIds.cameras,
    });
  }

  let boxFieldIssueCount = 0;
  settings.box_catalog.forEach((box, index) => {
    for (const [field, message] of Object.entries(boxFieldErrors(box, settings.box_catalog))) {
      boxFieldIssueCount += 1;
      issues.push({
        key: `box:${index}:${field}`,
        message: `箱クラス${index + 1}: ${message}`,
        targetId: settingsFieldId.box(index, field),
      });
    }
  });
  if (!settings.box_catalog.length) {
    issues.push({
      key: "box:none",
      message: "箱クラスを1件以上登録してください",
      targetId: settingsSectionIds.boxes,
    });
  }

  let palletFieldIssueCount = 0;
  for (const pallet of settings.pallets) {
    for (const [field, message] of Object.entries(palletFieldErrors(pallet, settings.box_catalog))) {
      palletFieldIssueCount += 1;
      issues.push({
        key: `pallet:${pallet.pallet_id}:${field}`,
        message: `${pallet.display_name || `パレット${pallet.pallet_number}`}: ${message}`,
        targetId: settingsFieldId.pallet(pallet.pallet_id, field),
        cameraId: pallet.camera_id,
      });
    }
  }
  if (boxFieldIssueCount === 0 && palletFieldIssueCount === 0
    && !validBoxConfiguration(settings.box_catalog, settings.pallets)) {
    issues.push({
      key: "box:configuration",
      message: "箱カタログとパレットの対象箱設定を修正してください",
      targetId: settingsSectionIds.boxes,
    });
  }

  for (const [field, message] of Object.entries(measurementFieldErrors(settings))) {
    issues.push({
      key: `measurement:${field}`,
      message,
      targetId: settingsFieldId.measurement(field),
    });
  }

  if (settings.method !== "pallet_plane_2roi"
    || !validFixedPalletLayout(settings.cameras, settings.pallets)) {
    issues.push({
      key: "pallet:layout",
      message: "各カメラにパレット1・2の2枠がある構成へ修正してください",
      targetId: settingsSectionIds.pallets,
    });
  } else if (!settings.pallets.some((pallet) => pallet.enabled)) {
    issues.push({
      key: "pallet:enabled",
      message: "少なくとも1つのパレットを測定対象にしてください",
      targetId: settingsFieldId.pallet(settings.pallets[0].pallet_id, "enabled"),
      cameraId: settings.pallets[0].camera_id,
    });
  }

  return issues;
}
