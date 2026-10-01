import ActionButton from "./ActionButton";
import CameraSelector from "./CameraSelector";
import ManagedStreamImage from "./ManagedStreamImage";
import type { CameraSettings, CameraStreamStatus, PalletSettings } from "./types";

type Props = {
  cameras: CameraStreamStatus[]; cameraConfigs: CameraSettings[]; pallets: PalletSettings[];
  selectedCameraId: string; onCameraChange: (cameraId: string) => void;
  show: boolean; revision: number; disabled: boolean;
  onShow: () => void; onHide: () => void;
};

export default function CameraPanel(props: Props) {
  const cameraConfig = props.cameraConfigs.find((camera) => camera.camera_id === props.selectedCameraId) ?? null;
  const camera = props.cameras.find((status) => status.camera?.camera_id === props.selectedCameraId) ?? null;
  const palletCount = props.pallets.filter((pallet) => (
    pallet.camera_id === props.selectedCameraId && pallet.enabled
  )).length;
  const streamUrl = `/camera-stream/${encodeURIComponent(props.selectedCameraId)}/live.mjpg?v=${props.revision}`;
  const showReason = props.disabled
    ? "別の処理が完了するまで映像を変更できません"
    : props.show
      ? "映像はすでに表示中です"
      : !cameraConfig ? "表示するカメラを選択してください" : undefined;
  const hideReason = props.disabled
    ? "別の処理が完了するまで映像を変更できません"
    : !props.show ? "映像はすでに非表示です" : undefined;
  return <section className="live-panel">
    <div className="field-camera-header">
      <CameraSelector cameras={props.cameraConfigs} selectedCameraId={props.selectedCameraId}
        label="現場表示カメラ" disabled={props.disabled} onChange={props.onCameraChange} />
      {cameraConfig && <div className="field-camera-summary">
        <strong>{cameraConfig.display_name}</strong>
        <span>{cameraConfig.camera_id}・対象パレット {palletCount}件</span>
      </div>}
    </div>
    <div className="live-heading"><div><span className={camera?.connected ? "camera-light active" : "camera-light"} />
      <strong>{camera?.connected ? "カメラサーバー接続中" : camera?.running ? "カメラ再接続中" : "カメラサーバー停止中"}</strong>
      {cameraConfig && <small>{cameraConfig.ip}:{cameraConfig.port}</small>}
      {camera?.running && <small>MJPEG閲覧 {camera.viewers}</small>}</div>
      <div className="live-actions"><ActionButton disabledReason={showReason} onClick={props.onShow}>
        {props.show ? "映像表示中" : "映像を表示"}
      </ActionButton>
        <ActionButton disabledReason={hideReason} onClick={props.onHide}>
          {props.show ? "映像を非表示" : "映像非表示中"}
        </ActionButton></div></div>
    {props.show ? <ManagedStreamImage className="live-preview" src={streamUrl}
      alt="現在のカメラ映像" />
      : <div className="live-placeholder">「映像を表示」を押すと現在映像が表示されます。</div>}
    {camera?.error && <p className="monitor-error">{camera.error}</p>}
  </section>;
}
