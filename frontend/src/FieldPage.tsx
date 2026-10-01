import CameraPanel from "./CameraPanel";
import FactoryMapDashboard from "./FactoryMapDashboard";
import MeasurementResults from "./MeasurementResults";
import type { CameraSettings, CameraStreamStatus, FactoryDashboard, Measurement, PalletSettings } from "./types";
import type { RemoteResourceStatus } from "./remoteResource";
import type { NoticeHandler } from "./uiNotice";

type Props = {
  view: "map" | "camera";
  busy: boolean; dirty: boolean;
  cameraConfigs: CameraSettings[]; pallets: PalletSettings[];
  cameras: CameraStreamStatus[]; selectedCameraId: string;
  onOpenMap: () => void; onOpenCamera: (cameraId: string) => void;
  result: Measurement | null; showLive: boolean; revision: number;
  dashboard: FactoryDashboard | null;
  dashboardStatus: RemoteResourceStatus;
  dashboardError: string | null;
  onShow: () => void; onHide: () => void;
  onRefreshDashboard: () => Promise<unknown>;
  onRetryDashboard: () => Promise<unknown>;
  onMessage: NoticeHandler;
};

export default function FieldPage(props: Props) {
  const detailOpen = props.view === "camera";
  const mapDisabledReason = props.busy ? "別の処理が完了するまでマップを編集できません"
    : props.dirty ? "未保存の設定を保存してからマップを編集してください" : undefined;
  const detailResult = props.result ? {
    ...props.result,
    camera_runs: props.result.camera_runs.filter((run) => run.camera_id === props.selectedCameraId),
    pallets: props.result.pallets.filter((pallet) => pallet.camera_id === props.selectedCameraId),
  } : null;
  return <>
    {detailOpen && <button className="back-to-map" onClick={props.onOpenMap}>← 工場マップへ戻る</button>}
    {props.dirty && <p className="warning">設定が未保存です。設定画面で保存してください。</p>}
    {!detailOpen && <FactoryMapDashboard dashboard={props.dashboard} streams={props.cameras}
      status={props.dashboardStatus} error={props.dashboardError}
      disabled={props.busy || props.dirty}
      disabledReason={mapDisabledReason}
      onOpenCamera={props.onOpenCamera}
      onRefresh={props.onRefreshDashboard} onRetry={props.onRetryDashboard}
      onMessage={props.onMessage} />}
    {detailOpen && <>
      <CameraPanel cameras={props.cameras} cameraConfigs={props.cameraConfigs} pallets={props.pallets}
        selectedCameraId={props.selectedCameraId} onCameraChange={props.onOpenCamera} show={props.showLive}
        revision={props.revision} disabled={props.busy}
        onShow={props.onShow} onHide={props.onHide} />
      <MeasurementResults result={detailResult} />
    </>}
  </>;
}
