import type { CameraSettings } from "./types";

type Props = {
  cameras: CameraSettings[];
  selectedCameraId: string;
  label: string;
  disabled?: boolean;
  className?: string;
  onChange: (cameraId: string) => void;
};

export default function CameraSelector({ cameras, selectedCameraId, label, disabled = false,
  className = "", onChange }: Props) {
  return <label className={`camera-picker ${className}`.trim()}>
    <span>{label}</span>
    <select value={selectedCameraId} disabled={disabled || cameras.length === 0}
      onChange={(event) => onChange(event.target.value)}>
      {cameras.length === 0 && <option value="">カメラが登録されていません</option>}
      {cameras.map((camera) => <option key={camera.camera_id} value={camera.camera_id}>
        {camera.display_name}（{camera.camera_id}）
      </option>)}
    </select>
  </label>;
}
