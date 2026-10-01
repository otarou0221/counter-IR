import type { CameraListItem } from "./cameraList";

const stateLabels = {
  normal: "正常",
  low_stock: "低在庫",
  unavailable: "確認必要",
};

function measurementText(item: CameraListItem["pallets"][number]): string {
  if (item.inventoryCount === null) return "箱数 未測定";
  const volume = item.volumeLiters === null ? "" : ` / ${item.volumeLiters.toFixed(1)}L`;
  return `${item.inventoryCount}箱${volume}`;
}

function cameraAriaLabel(item: CameraListItem): string {
  const pallets = item.pallets.map((pallet) => (
    `パレット${pallet.palletNumber} ${pallet.message} ${measurementText(pallet)}`
  )).join("、");
  return `${item.displayName}、${item.connected ? "接続中" : "切断中"}、${pallets}。現場用画面を開く`;
}

function measuredAtText(value: string | null): string {
  return value ? new Date(value).toLocaleString("ja-JP") : "未測定";
}

export default function FactoryCameraList({ items, onOpenCamera }: {
  items: CameraListItem[];
  onOpenCamera: (cameraId: string) => void;
}) {
  return <section className="factory-camera-list" aria-labelledby="factory-camera-list-title">
    <div className="factory-camera-list-heading">
      <h2 id="factory-camera-list-title">カメラ・パレット状態</h2>
      <p>Tabキーで選び、Enterキーで現場用画面を開けます。</p>
    </div>
    {items.length === 0
      ? <p className="factory-camera-list-empty">登録済みカメラはありません。</p>
      : <div className="factory-camera-list-grid">{items.map((item) => <button type="button"
        className={`factory-camera-card ${item.state}`} key={item.cameraId}
        aria-label={cameraAriaLabel(item)} onClick={() => onOpenCamera(item.cameraId)}>
        <span className="factory-camera-card-heading">
          <strong>{item.displayName}</strong>
          <span className={`camera-state-badge ${item.state}`}>{stateLabels[item.state]}</span>
        </span>
        <span className="factory-camera-meta">{item.cameraId}・{item.connected ? "接続中" : "切断中"}</span>
        <span className="factory-camera-meta">{item.location}</span>
        <span className="factory-camera-meta">最終測定 {measuredAtText(item.lastMeasuredAt)}</span>
        <span className="factory-camera-pallets">{item.pallets.map((pallet) => <span
          className={`factory-camera-pallet ${pallet.state}`} key={pallet.palletSlotId}>
          <span><b>P{pallet.palletNumber}</b> {pallet.displayName}</span>
          <span>{pallet.message}・{measurementText(pallet)}</span>
        </span>)}</span>
        <span className="factory-camera-open">現場用画面を開く →</span>
      </button>)}</div>}
  </section>;
}
