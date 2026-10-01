import { boxRuleLabels, normalizeBoxLabel } from "./boxCatalog";
import type { BoxClassSpec, PalletSettings } from "./types";

export type PalletFieldErrors = Partial<Record<
  "display_name" | "low_stock_threshold_liters" | "email_rearm_margin_liters" | "boxes",
  string
>>;

export function palletFieldErrors(
  pallet: PalletSettings,
  catalog: BoxClassSpec[],
): PalletFieldErrors {
  const errors: PalletFieldErrors = {};
  if (!pallet.display_name.trim()) errors.display_name = "パレット表示名を入力してください";
  if (!Number.isFinite(pallet.low_stock_threshold_liters) || pallet.low_stock_threshold_liters < 1) {
    errors.low_stock_threshold_liters = "低在庫警告体積を1L以上で入力してください";
  }
  if (!Number.isFinite(pallet.email_rearm_margin_liters) || pallet.email_rearm_margin_liters < 1) {
    errors.email_rearm_margin_liters = "メール再有効化増加量を1L以上で入力してください";
  }
  const known = new Set(catalog.map((box) => normalizeBoxLabel(box.label)));
  const selected = boxRuleLabels(pallet).map(normalizeBoxLabel);
  if (!selected.length || selected.some((label) => !known.has(label))) {
    errors.boxes = "単品箱または混在可能グループを設定してください";
  } else if (pallet.mixed_box_groups.some((group) => {
    const labels = group.map(normalizeBoxLabel);
    return labels.length < 2 || new Set(labels).size !== labels.length;
  })) {
    errors.boxes = "混在可能グループには異なる箱を2種類以上設定してください";
  } else if (new Set(pallet.mixed_box_groups.map((group) => (
    group.map(normalizeBoxLabel).sort().join("\u0000")
  ))).size !== pallet.mixed_box_groups.length) {
    errors.boxes = "同じ混在可能グループが重複しています";
  } else if (!selected.includes(normalizeBoxLabel(pallet.reference_box_label))) {
    errors.boxes = "対象箱の中から基準箱を選択してください";
  }
  return errors;
}
