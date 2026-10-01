import { artifactUrl } from "./links";
import type { Measurement } from "./types";

function countsText(counts: Record<string, number>): string {
  const values = Object.entries(counts).map(([label, count]) => `${label}: ${count}箱`);
  return values.length ? values.join(" / ") : "箱なし";
}

type Props = {
  result: Measurement | null;
  showDiagnosticLinks?: boolean;
};

export default function MeasurementResults({ result, showDiagnosticLinks = false }: Props) {
  if (!result) return null;
  return <section className="results">{result.pallets.map((pallet) => <article key={`${pallet.camera_id}:${pallet.pallet_id}`}>
    <h2>パレット {pallet.pallet_number} <small>{pallet.camera_id}</small></h2>
    {pallet.is_low_stock && <p className="low-stock-warning">
      低在庫：残体積 {pallet.volume_liters.toFixed(3)} L
      {pallet.low_stock_threshold_liters !== null
        ? `（警告しきい値 ${pallet.low_stock_threshold_liters.toFixed(3)} L以下）` : ""}
    </p>}
    <strong>{pallet.estimated_boxes.toFixed(0)} 箱</strong>
    <p>3D実測 {pallet.volume_liters.toFixed(3)} L / 平面RMSE {pallet.plane_rmse_mm.toFixed(2)} mm</p>
    {pallet.box_combination && <div className="box-fit-result">
      <b>推定した箱の内訳: {countsText(pallet.box_combination.best.counts)}</b>
      <span>組合せ体積 {pallet.box_combination.best.fitted_volume_liters.toFixed(3)} L
        （差 {pallet.box_combination.best.residual_volume_liters.toFixed(3)} L）</span>
      {pallet.box_combination.ambiguous && <span className="warning">体積だけでは内訳を一意に決められません。</span>}
      {pallet.box_combination.alternatives.length > 1 && <details><summary>候補を表示</summary>
        <ol>{pallet.box_combination.alternatives.map((candidate, index) => <li key={index}>
          {countsText(candidate.counts)} / 差 {candidate.residual_volume_liters.toFixed(3)} L
        </li>)}</ol></details>}
    </div>}
    <p>局所突起除外 {pallet.protrusion_components}個・{pallet.protrusion_volume_liters.toFixed(3)} L</p>
    {showDiagnosticLinks && (pallet.plot_path || pallet.debug_stages_path) && <div className="result-links">
      {pallet.plot_path && <a href={artifactUrl(pallet.plot_path)} target="_blank">最終3D診断</a>}
      {pallet.debug_stages_path && <a href={artifactUrl(pallet.debug_stages_path)} target="_blank">段階別3D診断</a>}
    </div>}
  </article>)}</section>;
}
