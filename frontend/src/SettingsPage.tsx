import BackToTopButton from "./BackToTopButton";
import type { NormalizedRoi } from "./roi";
import RoiSettingsPanel from "./RoiSettingsPanel";
import SettingsCameraSelector from "./SettingsCameraSelector";
import SettingsPanel from "./SettingsPanel";
import SettingsSaveBar from "./SettingsSaveBar";
import type { SettingsValidationIssue } from "./settingsValidation";
import type { CameraStreamStatus, RoiReferenceCapture, SavedCapture, SystemSettings } from "./types";
import type { NoticeHandler } from "./uiNotice";
import { useSettingsIssueNavigation } from "./useSettingsIssueNavigation";

type Props = {
  busy: boolean; monitoring: boolean; dirty: boolean; valid: boolean;
  validationMessage?: string;
  validationIssues: SettingsValidationIssue[];
  config: SystemSettings | null; savedConfig: SystemSettings | null;
  cameras: CameraStreamStatus[];
  selectedCameraId: string; onCameraChange: (cameraId: string) => void;
  roiReferences: RoiReferenceCapture[];
  floorCaptures: SavedCapture[]; floorCaptureLimit: number;
  calibratedCameraIds: string[];
  onSave: () => void; onSaveRois: () => void; onRetryCalibration: () => void;
  onCaptureRoiImage: () => void;
  onSelectFloorCapture: (captureId: string) => void;
  onMessage: NoticeHandler; onConfigChange: (settings: SystemSettings) => void;
  onRoiChange: (palletId: number, roi: NormalizedRoi) => void;
  onEnabledChange: (palletId: number, enabled: boolean) => void;
};

const settingsPageTopId = "settings-page-top";

export default function SettingsPage(props: Props) {
  const selectValidationIssue = useSettingsIssueNavigation(
    props.selectedCameraId,
    props.onCameraChange,
  );
  const calibrationDisabled = props.busy || props.monitoring;
  const calibrationDisabledReason = props.busy ? "別の処理が完了するまで校正設定を変更できません"
    : props.monitoring ? "常時監視を停止してから校正設定を変更してください"
      : !props.valid ? "入力エラーを修正してから校正を実行してください" : undefined;

  return <div className="settings-page">
    <SettingsCameraSelector id={settingsPageTopId}
      config={props.config} selectedCameraId={props.selectedCameraId}
      disabled={props.busy} onChange={props.onCameraChange} />
    <RoiSettingsPanel config={props.config} cameras={props.cameras} selectedCameraId={props.selectedCameraId}
      disabled={calibrationDisabled || !props.valid} disabledReason={calibrationDisabledReason}
      dirty={props.dirty} references={props.roiReferences}
      floorCaptures={props.floorCaptures} floorCaptureLimit={props.floorCaptureLimit}
      calibrated={props.calibratedCameraIds.includes(props.selectedCameraId)}
      onCapture={props.onCaptureRoiImage} onSave={props.onSaveRois}
      onRetryCalibration={props.onRetryCalibration} onMessage={props.onMessage}
      onSelectFloor={props.onSelectFloorCapture}
      onRoiChange={props.onRoiChange} onEnabledChange={props.onEnabledChange} />
    <SettingsPanel settings={props.config} savedSettings={props.savedConfig} dirty={props.dirty}
      disabled={props.busy} monitoring={props.monitoring} selectedCameraId={props.selectedCameraId}
      onCameraChange={props.onCameraChange} onSettingsChange={props.onConfigChange}
      />
    {props.config && <SettingsSaveBar busy={props.busy} monitoring={props.monitoring} dirty={props.dirty}
      valid={props.valid} validationMessage={props.validationMessage}
      validationIssues={props.validationIssues} onIssueSelect={selectValidationIssue}
      onSave={props.onSave} />}
    <BackToTopButton targetId={settingsPageTopId} label="設定画面の上部へ戻る" />
  </div>;
}
