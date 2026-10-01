import RoiEditor from "./RoiEditor";
import type { NormalizedRoi } from "./roi";
import type { CameraStreamStatus, RoiReferenceCapture, SavedCapture, SystemSettings } from "./types";
import type { NoticeHandler } from "./uiNotice";

export default function RoiSettingsPanel({ config, cameras, selectedCameraId, disabled, disabledReason, dirty, references,
  floorCaptures, floorCaptureLimit, calibrated, onCapture, onSelectFloor, onRoiChange, onEnabledChange,
  onSave, onRetryCalibration, onMessage }: {
  config: SystemSettings | null;
  cameras: CameraStreamStatus[];
  selectedCameraId: string;
  disabled: boolean;
  disabledReason?: string;
  dirty: boolean;
  references: RoiReferenceCapture[];
  floorCaptures: SavedCapture[];
  floorCaptureLimit: number;
  calibrated: boolean;
  onCapture: () => void;
  onSelectFloor: (captureId: string) => void;
  onRoiChange: (palletId: number, roi: NormalizedRoi) => void;
  onEnabledChange: (palletId: number, enabled: boolean) => void;
  onSave: () => void;
  onRetryCalibration: () => void;
  onMessage: NoticeHandler;
}) {
  const camera = config?.cameras.find((item) => item.camera_id === selectedCameraId) ?? null;
  const status = cameras.find((item) => item.camera?.camera_id === selectedCameraId) ?? null;
  const pallets = config?.pallets.filter((item) => item.camera_id === selectedCameraId) ?? [];
  const cameraReferences = references.filter((item) => item.camera_id === selectedCameraId);
  const cameraFloorCaptures = floorCaptures.filter((item) => item.camera_id === selectedCameraId);
  return <section className="live-panel roi-settings-panel">
    {camera && pallets.length > 0
      ? <RoiEditor pallets={pallets} cameraName={camera.display_name} connected={status?.connected ?? false}
        disabled={disabled} disabledReason={disabledReason} dirty={dirty}
        references={cameraReferences} onCapture={onCapture}
        floorCaptures={cameraFloorCaptures} floorCaptureLimit={floorCaptureLimit} onSelectFloor={onSelectFloor}
        calibrated={calibrated} onRoiChange={onRoiChange} onEnabledChange={onEnabledChange}
        onSave={onSave} onRetryCalibration={onRetryCalibration} onMessage={onMessage} />
      : <div className="live-placeholder">設定対象カメラを選択してください。</div>}
    {status?.error && <p className="monitor-error">{status.error}</p>}
  </section>;
}
