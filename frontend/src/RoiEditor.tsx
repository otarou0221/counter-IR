import { useState } from "react";
import ActionButton from "./ActionButton";
import { artifactUrl } from "./links";
import type { NormalizedRoi } from "./roi";
import StaticImageRectangleEditor, { type ImageRectangle } from "./StaticImageRectangleEditor";
import type { PalletSettings, RoiReferenceCapture, SavedCapture } from "./types";
import type { NoticeHandler } from "./uiNotice";

type Props = {
  pallets: PalletSettings[];
  cameraName: string;
  connected: boolean;
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
};

export default function RoiEditor({ pallets, cameraName, connected, disabled, disabledReason, dirty, references,
  floorCaptures, floorCaptureLimit, calibrated, onCapture, onSelectFloor, onRoiChange, onEnabledChange,
  onSave, onRetryCalibration, onMessage }: Props) {
  const [palletId, setPalletId] = useState(pallets[0]?.pallet_id ?? 1);
  const [selectedFloorId, setSelectedFloorId] = useState("");
  const selected = pallets.find((pallet) => pallet.pallet_id === palletId) ?? pallets[0];
  if (!selected) return null;
  const activePalletId = selected.pallet_id;
  const rectangles: ImageRectangle[] = pallets.map((pallet) => ({
    id: `${pallet.pallet_id}-plane_roi`,
    label: `P${pallet.pallet_number} 床基準ROI`,
    roi: pallet.plane_roi,
    className: `pallet-${pallet.pallet_number} plane_roi`,
    muted: !pallet.enabled || pallet.pallet_id !== activePalletId,
  }));
  const active = rectangles.find((rectangle) => rectangle.id === `${activePalletId}-plane_roi`)!;
  const reference = references[0] ?? null;
  const capturedAt = reference?.captured_at ? new Date(reference.captured_at).toLocaleString("ja-JP") : null;
  const savedFloorId = floorCaptures.some((item) => item.capture_id === selectedFloorId)
    ? selectedFloorId
    : floorCaptures.find((item) => item.capture_id === reference?.capture_id)?.capture_id
      ?? floorCaptures[0]?.capture_id ?? "";

  return <div className="roi-editor">
    <div className="roi-reference-heading"><strong>{cameraName}の床基準ROIを設定中</strong>
      <span>{connected ? "カメラ接続中" : "カメラ再接続中"}</span></div>
    <div className="roi-toolbar">
      <div className="roi-pallet-tabs">{pallets.map((pallet) => <button type="button" key={pallet.pallet_id}
        className={activePalletId === pallet.pallet_id ? "selected" : ""} disabled={disabled}
        title={disabled ? disabledReason : undefined}
        onClick={() => setPalletId(pallet.pallet_id)}>パレット {pallet.pallet_number}</button>)}</div>
      <label className="pallet-enabled"><input type="checkbox" checked={selected.enabled} disabled={disabled}
        onChange={(event) => onEnabledChange(activePalletId, event.target.checked)} />このパレットを測定する</label>
    </div>
    <p className="roi-help">パレットを置いていない床の定位置を囲みます。床上の3D外周をパレット高さ分だけ平行移動し、ROI全体を体積測定に使います。</p>
    <div className="empty-reference-actions">
      <div className="roi-capture-actions"><ActionButton type="button"
        disabledReason={disabled ? disabledReason : !connected ? "カメラの接続完了を待ってください" : undefined}
        onClick={onCapture}>{reference ? "床画像を撮影（撮り直す）" : "床画像を撮影"}</ActionButton>
        <span>新しくActive IR＋Depthを撮影</span></div>
      <div className="saved-empty-selector"><label>保存済み床撮影
        <select value={savedFloorId} disabled={disabled || floorCaptures.length === 0}
          onChange={(event) => setSelectedFloorId(event.target.value)}>
          {floorCaptures.length === 0 && <option value="">保存済み撮影はありません</option>}
          {floorCaptures.map((item) => <option key={item.capture_id} value={item.capture_id}>
            {new Date(item.captured_at).toLocaleString("ja-JP")} / {item.frame_count}枚 / {item.color_shape[1]}×{item.color_shape[0]}
            {item.capture_id === reference?.capture_id ? "（使用中）" : ""}
          </option>)}
        </select></label>
        <ActionButton type="button" disabledReason={disabled ? disabledReason
          : !savedFloorId ? "保存済み床撮影を選択してください"
            : savedFloorId === reference?.capture_id ? "選択した撮影はすでに使用中です" : undefined}
          onClick={() => onSelectFloor(savedFloorId)}>選択した撮影を使用</ActionButton>
        <strong>{floorCaptures.length}/{floorCaptureLimit}件</strong>
      </div>
    </div>
    {reference && <div className="roi-reference-meta">使用中の撮影: {capturedAt ?? "日時不明"} / {reference.capture_id}</div>}
    {reference
      ? <StaticImageRectangleEditor imageUrl={artifactUrl(reference.rgb_path)} disabled={disabled}
        rectangles={rectangles} activeRectangle={active}
        onChange={(roi) => { onRoiChange(activePalletId, roi); onMessage(`パレット${selected.pallet_number}の床基準ROIを変更しました。保存してください`, "warning"); }}
        onMessage={onMessage} />
      : <div className="live-placeholder">「床画像を撮影」を押すと、保存画像上でROIを選択できます。</div>}
    <div className="roi-footer"><span>{calibrated ? "校正済み" : "未校正"}</span><div>
      {!dirty && reference && !calibrated && <ActionButton type="button"
        disabledReason={disabled ? disabledReason : undefined}
        onClick={onRetryCalibration}>校正を再試行</ActionButton>}
      <ActionButton type="button" className="roi-save" disabledReason={disabled ? disabledReason
        : !reference ? "床画像を撮影または選択してください"
          : !dirty ? "ROI設定に未保存の変更はありません" : undefined}
        onClick={onSave}>ROI設定を保存して校正</ActionButton></div></div>
    <p className="roi-note">ROIを保存すると床平面を校正し、その3D外周を設定したパレット高さ分だけ持ち上げます。</p>
  </div>;
}
