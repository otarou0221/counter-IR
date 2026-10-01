import { boxRuleLabels, normalizeBoxLabel } from "./boxCatalog";
import type { BoxClassSpec, PalletSettings } from "./types";

export type BoxFieldErrors = Partial<Record<"label" | "width_mm" | "depth_mm" | "height_mm", string>>;

export function boxFieldErrors(box: BoxClassSpec, catalog: BoxClassSpec[]): BoxFieldErrors {
  const errors: BoxFieldErrors = {};
  const label = normalizeBoxLabel(box.label);
  if (!label) errors.label = "箱名を入力してください";
  else if (catalog.filter((item) => normalizeBoxLabel(item.label) === label).length > 1) {
    errors.label = "同じ箱名が重複しています";
  }
  for (const [field, name] of [
    ["width_mm", "幅"], ["depth_mm", "奥行"], ["height_mm", "高さ"],
  ] as const) {
    if (!Number.isFinite(box[field]) || box[field] < 1) errors[field] = `${name}を1mm以上で入力してください`;
  }
  return errors;
}

export function validBoxConfiguration(catalog: BoxClassSpec[], pallets: PalletSettings[]): boolean {
  const catalogLabels = new Set(catalog.map((item) => normalizeBoxLabel(item.label)));
  const validCatalog = catalog.length > 0
    && catalog.every((item) => Object.keys(boxFieldErrors(item, catalog)).length === 0);
  return validCatalog && pallets.every((pallet) => {
    const selected = boxRuleLabels(pallet).map(normalizeBoxLabel);
    return selected.length > 0
      && selected.every((label) => catalogLabels.has(label))
      && selected.includes(normalizeBoxLabel(pallet.reference_box_label));
  });
}
