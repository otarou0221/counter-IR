import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import FactoryMapCanvas from "./factory-map/FactoryMapCanvas";
import FactoryCameraList from "./factory-map/FactoryCameraList";
import FactoryMapToolbar from "./factory-map/FactoryMapToolbar";
import FactoryMapUpload from "./factory-map/FactoryMapUpload";
import { buildCameraList } from "./factory-map/cameraList";
import { effectivePalletState, palletMarkers } from "./factory-map/presentation";
import { useFactoryMapEditor } from "./factory-map/useFactoryMapEditor";
import type {
  CameraStreamStatus,
  FactoryDashboard,
  FactoryMapSummary,
} from "./types";
import type { RemoteResourceStatus } from "./remoteResource";
import type { NoticeHandler } from "./uiNotice";

type Props = {
  dashboard: FactoryDashboard | null;
  status: RemoteResourceStatus;
  error: string | null;
  streams: CameraStreamStatus[];
  disabled: boolean;
  disabledReason?: string;
  onOpenCamera: (cameraId: string) => void;
  onRefresh: () => Promise<unknown>;
  onRetry: () => Promise<unknown>;
  onMessage: NoticeHandler;
};

export default function FactoryMapDashboard(props: Props) {
  if (!props.dashboard) {
    return <section className="factory-dashboard">
      <div className={`dashboard-load-state ${props.status}`} aria-live="polite"
        aria-busy={props.status === "loading"}>
        {props.status === "loading" ? <>
          <span className="busy-indicator" aria-hidden="true" />
          <strong>工場マップを読み込んでいます</strong>
        </> : <>
          <h2>工場マップを読み込めませんでした</h2>
          <p>{props.error}</p>
          <button type="button" onClick={() => void props.onRetry()}>再読み込み</button>
        </>}
      </div>
    </section>;
  }

  return <FactoryMapDashboardContent {...props} dashboard={props.dashboard} />;
}

function FactoryMapDashboardContent(props: Props & { dashboard: FactoryDashboard }) {
  const maps = props.dashboard?.maps ?? [];
  const cameras = props.dashboard?.cameras ?? [];
  const [selectedMapId, setSelectedMapId] = useState<number | null>(null);
  const markers = useMemo(() => palletMarkers(cameras), [cameras]);
  const cameraList = useMemo(() => buildCameraList(
    cameras,
    props.streams,
    props.dashboard?.monitor_running ?? false,
  ), [cameras, props.dashboard?.monitor_running, props.streams]);

  useEffect(() => {
    if (!maps.length) {
      setSelectedMapId(null);
      return;
    }
    if (selectedMapId === null
      || !maps.some((item) => item.factory_map_id === selectedMapId)) {
      setSelectedMapId(maps[0].factory_map_id);
    }
  }, [maps, selectedMapId]);

  const selectedMap = maps.find((item) => item.factory_map_id === selectedMapId) ?? null;
  const editor = useFactoryMapEditor(markers, selectedMap);
  const mapMarkers = markers.filter(({ pallet }) => (
    editor.positions[pallet.pallet_slot_id]
  ));
  const visibleStates = mapMarkers.map(({ camera, pallet }) => effectivePalletState(
    camera,
    pallet,
    props.streams,
    props.dashboard?.monitor_running ?? false,
  ));
  const normalCount = visibleStates.filter((item) => item.state === "normal").length;
  const lowCount = visibleStates.filter((item) => item.state === "low_stock").length;
  const unavailableCount = visibleStates.filter((item) => item.state === "unavailable").length;
  const unplacedMarkers = editor.editMode ? markers.filter(({ pallet }) => (
    !pallet.placement || (
      pallet.placement.factory_map_id === selectedMapId
      && !editor.draft[pallet.pallet_slot_id]
    )
  )) : [];

  const mapCreated = async (created: FactoryMapSummary) => {
    await props.onRefresh();
    setSelectedMapId(created.factory_map_id);
  };
  const savePlacements = async () => {
    if (!selectedMap) return;
    await api(`/api/dashboard/maps/${selectedMap.factory_map_id}/placements`, {
      method: "PUT",
      body: JSON.stringify({
        placements: Object.entries(editor.draft).map(([pallet_slot_id, position]) => ({
          pallet_slot_id: Number(pallet_slot_id),
          position_x_ratio: position.x / selectedMap.image_width,
          position_y_ratio: position.y / selectedMap.image_height,
        })),
      }),
    });
    editor.finishSaving();
    await props.onRefresh();
    props.onMessage("パレット配置を保存しました", "success");
  };
  const deleteMap = async () => {
    if (!selectedMap) return;
    const confirmed = window.confirm(
      `「${selectedMap.display_name}」を削除しますか？\nマップ画像とパレット配置が削除されます。`,
    );
    if (!confirmed) return;
    await api<FactoryMapSummary>(`/api/dashboard/maps/${selectedMap.factory_map_id}`, {
      method: "DELETE",
    });
    editor.cancelEditing();
    setSelectedMapId(null);
    await props.onRefresh();
    props.onMessage(`工場マップを削除しました: ${selectedMap.display_name}`, "success");
  };

  return <section className="factory-dashboard">
    {props.status === "stale" && <div className="dashboard-stale-warning" role="status">
      <div><strong>最新情報を取得できません</strong>
        <span>最後に取得できた工場マップを表示しています。{props.error}</span></div>
      <button type="button" onClick={() => void props.onRetry()}>再読み込み</button>
    </div>}
    <div className="dashboard-summary">
      <div><span className="summary-dot normal" /><strong>{normalCount}</strong><small>正常</small></div>
      <div><span className="summary-dot low" /><strong>{lowCount}</strong><small>低在庫</small></div>
      <div><span className="summary-dot unavailable" /><strong>{unavailableCount}</strong><small>確認必要</small></div>
    </div>

    {!maps.length && <div className="map-empty-state">
      <h2>工場マップはまだ登録されていません</h2>
      <p>Windowsなどで作成した簡易図面をPNG形式で登録できます。</p>
      <FactoryMapUpload disabled={props.disabled} disabledReason={props.disabledReason}
        onError={(message) => props.onMessage(message, "error")}
        onCreated={async (created) => {
          await mapCreated(created);
          props.onMessage("工場マップを登録しました。配置編集からパレットを置いてください", "success");
        }} />
    </div>}

    {selectedMap && <>
      <FactoryMapToolbar maps={maps} selectedMap={selectedMap}
        editMode={editor.editMode} disabled={props.disabled}
        disabledReason={props.disabledReason}
        selectedMarker={editor.selectedMarker} onSelectMap={setSelectedMapId}
        onStartEditing={editor.startEditing}
        onSave={() => void savePlacements().catch((error: Error) => {
          props.onMessage(error.message, "error");
        })}
        onCancel={editor.cancelEditing} onRemoveSelected={editor.removeSelected}
        onDeleteMap={() => void deleteMap().catch((error: Error) => {
          props.onMessage(error.message, "error");
        })} />

      {editor.editMode && <div className="unplaced-cameras">
        <strong>未配置パレット</strong>
        {unplacedMarkers.length ? unplacedMarkers.map(({ camera, pallet }) => <button
          key={pallet.pallet_slot_id} draggable
          onDragStart={(event) => {
            event.dataTransfer.setData(
              "text/pallet-slot-id",
              String(pallet.pallet_slot_id),
            );
          }}>
          {camera.display_name} P{pallet.pallet_number}
        </button>) : <span>すべて配置済みです</span>}
        <small>パレット名を工場マップへドラッグしてください。</small>
      </div>}

      <FactoryMapCanvas map={selectedMap} markers={markers}
        streams={props.streams}
        monitorRunning={props.dashboard?.monitor_running ?? false}
        positions={editor.positions} editMode={editor.editMode}
        selectedMarker={editor.selectedMarker}
        onSelectMarker={editor.setSelectedMarker}
        onSetPosition={editor.setPosition} onOpenCamera={props.onOpenCamera} />

      <div className="map-legend">
        <span><i className="normal" />正常</span>
        <span><i className="low" />低在庫</span>
        <span><i className="unavailable" />測定エラー・切断・未測定・監視停止</span>
      </div>

      <details className="map-add-floor">
        <summary>別フロアのマップを追加</summary>
        <FactoryMapUpload disabled={props.disabled || editor.editMode}
          disabledReason={props.disabledReason ?? (editor.editMode ? "配置編集を終了してから追加してください" : undefined)}
          onError={(message) => props.onMessage(message, "error")} onCreated={async (created) => {
            await mapCreated(created);
            props.onMessage("新しいフロアマップを登録しました", "success");
          }} />
      </details>
    </>}
    <FactoryCameraList items={cameraList} onOpenCamera={props.onOpenCamera} />
  </section>;
}
