import { useEffect, useState } from "react";
import { api } from "./api";
import ActionButton from "./ActionButton";
import {
  currentCaptureLabel,
  DEBUG_CAPTURE_PAGE_SIZE,
  floorCaptureLabel,
} from "./debugCaptures";
import { artifactUrl } from "./links";
import CameraSelector from "./CameraSelector";
import MeasurementResults from "./MeasurementResults";
import type { Measurement, SavedCapture, SystemSettings } from "./types";
import type { NoticeHandler } from "./uiNotice";
import { useDebugCaptureCatalog } from "./useDebugCaptureCatalog";

type Props = {
  systemBusy: boolean;
  monitoring: boolean;
  dirty: boolean;
  config: SystemSettings | null;
  selectedCameraId: string;
  onCameraChange: (cameraId: string) => void;
  onMessage: NoticeHandler;
};

export default function DebugPage({ systemBusy, monitoring, dirty, config,
  selectedCameraId, onCameraChange, onMessage }: Props) {
  const [baselineId, setBaselineId] = useState("");
  const [currentId, setCurrentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Measurement | null>(null);
  const activeCameraId = config?.cameras.some((camera) => camera.camera_id === selectedCameraId)
    ? selectedCameraId : config?.cameras[0]?.camera_id ?? "";
  const { catalog, loading: catalogLoading, refresh, loadMore } = useDebugCaptureCatalog(
    activeCameraId,
    onMessage,
  );
  const floor = catalog.floor_captures;
  const current = catalog.current_captures;
  const selectedBaselineId = floor.some((item) => item.capture_id === baselineId)
    ? baselineId : floor[0]?.capture_id ?? "";
  const selectedCurrentId = current.some((item) => item.capture_id === currentId)
    ? currentId : current[0]?.capture_id ?? "";
  const blockedReason = systemBusy ? "別の処理が完了するまで診断できません"
    : monitoring ? "常時監視を停止してから診断してください"
      : dirty ? "未保存の設定を保存してから診断してください" : undefined;
  useEffect(() => {
    setBaselineId("");
    setCurrentId("");
    setResult(null);
  }, [activeCameraId]);
  const captureCurrent = async () => {
    if (!activeCameraId) return onMessage("診断するカメラを選択してください", "warning");
    setBusy(true); onMessage(`${activeCameraId}を撮影し、段階別3D診断を生成中です`);
    try {
      const measured = await api<Measurement>("/api/debug/capture-current", {
        method: "POST", body: JSON.stringify({ camera_id: activeCameraId }),
      });
      setResult(measured);
      const capturedId = measured.camera_runs.find((run) => run.camera_id === activeCameraId)?.current_capture_id;
      if (capturedId) setCurrentId(capturedId);
      await refresh(false);
      onMessage(`現在撮影の段階別3Dを生成しました: ${measured.measurement_id}`, "success");
    } catch (error) { onMessage(error instanceof Error ? error.message : String(error), "error"); }
    finally { setBusy(false); }
  };
  const replay = async () => {
    if (!selectedBaselineId || !selectedCurrentId) return onMessage("床基準撮影と積載撮影を選択してください", "warning");
    setBusy(true); onMessage("保存済み撮影を段階別に再解析中です");
    try {
      const measured = await api<Measurement>("/api/debug/replay", {
        method: "POST", body: JSON.stringify({
          baseline_capture_id: selectedBaselineId,
          current_capture_id: selectedCurrentId,
        }),
      });
      setResult(measured); onMessage(`再解析完了: ${measured.measurement_id}`, "success");
    } catch (error) { onMessage(error instanceof Error ? error.message : String(error), "error"); }
    finally { setBusy(false); }
  };
  const selected = [
    floor.find((item) => item.capture_id === selectedBaselineId),
    current.find((item) => item.capture_id === selectedCurrentId),
  ].filter(Boolean) as SavedCapture[];
  return <>
    <section className="debug-panel">
      <div className="config-heading"><h2>カメラ撮影診断</h2></div>
      <p>診断・再解析するカメラを選びます。撮影と保存画像の一覧は、ここで選んだ同じカメラを使用します。</p>
      <div className="debug-current-actions"><CameraSelector cameras={config?.cameras ?? []}
        selectedCameraId={activeCameraId} label="診断・再解析するカメラ" disabled={busy}
        onChange={onCameraChange} />
        <ActionButton className="primary" disabledReason={busy ? "診断処理を実行中です"
          : blockedReason ?? (!activeCameraId ? "診断するカメラを選択してください" : undefined)}
          onClick={() => void captureCurrent()}>選択中のカメラで撮影して段階別3Dを生成</ActionButton></div>
      <hr />
      <div className="config-heading"><h2>保存データ再解析</h2><ActionButton
        disabledReason={busy ? "診断処理を実行中です"
          : catalogLoading ? "保存撮影を読み込み中です" : undefined}
        onClick={() => void refresh()}>一覧を更新</ActionButton></div>
      <p>現場用の校正状態は変更せず、{activeCameraId || "選択中カメラ"}の保存済み撮影を現在の測定方式とROI設定で再計算します。</p>
      <div className="debug-selectors">
        <label>床基準撮影<select value={selectedBaselineId} disabled={catalogLoading && floor.length === 0}
          onChange={(event) => setBaselineId(event.target.value)}>
          <option value="">{catalogLoading ? "読み込み中です" : "保存済み床撮影はありません"}</option>
          {floor.map((item) => <option key={item.capture_id} value={item.capture_id}>{floorCaptureLabel(item)}</option>)}</select></label>
        <label>積載後の撮影<select value={selectedCurrentId} disabled={catalogLoading && current.length === 0}
          onChange={(event) => setCurrentId(event.target.value)}>
          <option value="">{catalogLoading ? "読み込み中です" : "保存済み積載後撮影はありません"}</option>
          {current.map((item) => <option key={item.capture_id} value={item.capture_id}>{currentCaptureLabel(item)}</option>)}</select></label>
      </div>
      <div className="debug-catalog-pagination">
        <span>積載後撮影を新しい順に{current.length}件表示中
          {catalog.current_capture_limit > 0 && `（最大${catalog.current_capture_limit}件）`}</span>
        {catalog.current_has_more && <ActionButton
          disabledReason={catalogLoading ? "保存撮影を読み込み中です" : undefined}
          onClick={() => void loadMore()}>さらに{DEBUG_CAPTURE_PAGE_SIZE}件読み込む</ActionButton>}
      </div>
      <div className="debug-previews">{selected.map((item) => <figure key={item.capture_id}><img src={artifactUrl(item.rgb_path)} /><figcaption>{item.purpose === "floor" ? "床基準" : "積載後"}</figcaption></figure>)}</div>
      <ActionButton className="primary" disabledReason={busy ? "診断処理を実行中です"
        : blockedReason ?? (!selectedBaselineId || !selectedCurrentId ? "床基準撮影と積載後撮影を選択してください" : undefined)}
        onClick={() => void replay()}>選択した撮影から段階別3Dを生成</ActionButton>
      {blockedReason && <p className="warning">{blockedReason}</p>}
    </section>
    <MeasurementResults result={result} showDiagnosticLinks />
  </>;
}
