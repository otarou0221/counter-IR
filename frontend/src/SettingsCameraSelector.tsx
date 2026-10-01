import CameraSelector from "./CameraSelector";
import type { SystemSettings } from "./types";

export default function SettingsCameraSelector({ id, config, selectedCameraId, disabled, onChange }: {
  id?: string;
  config: SystemSettings | null;
  selectedCameraId: string;
  disabled: boolean;
  onChange: (cameraId: string) => void;
}) {
  const selected = config?.cameras.find((camera) => camera.camera_id === selectedCameraId) ?? null;
  return <section id={id} tabIndex={id ? -1 : undefined} className="settings-camera-selector">
    <CameraSelector cameras={config?.cameras ?? []} selectedCameraId={selectedCameraId}
      label="設定対象カメラ" disabled={disabled || !config} onChange={onChange} />
    {selected && <div><strong>{selected.display_name}を設定中</strong>
      <span>{selected.ip}:{selected.port}</span></div>}
  </section>;
}
