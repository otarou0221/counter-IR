import type { BoxClassSpec, PalletSettings } from "./types";

export const normalizeBoxLabel = (value: string): string => value.trim().toLocaleLowerCase();

export function boxRuleLabels(pallet: PalletSettings): string[] {
  const labels = [...pallet.single_box_labels, ...pallet.mixed_box_groups.flat()];
  return labels.filter((label, index) => labels.findIndex(
    (candidate) => normalizeBoxLabel(candidate) === normalizeBoxLabel(label),
  ) === index);
}

export function createBoxClassSpec(catalog: BoxClassSpec[]): BoxClassSpec {
  const existing = new Set(catalog.map((item) => normalizeBoxLabel(item.label)));
  let sequence = catalog.length + 1;
  while (existing.has(`box_${sequence}`)) sequence += 1;
  return { label: `box_${sequence}`, width_mm: 0, depth_mm: 0, height_mm: 0 };
}

export function renamePalletBoxLabel(
  pallets: PalletSettings[], oldLabel: string, newLabel: string,
): PalletSettings[] {
  const oldKey = normalizeBoxLabel(oldLabel);
  return pallets.map((pallet) => ({
    ...pallet,
    single_box_labels: pallet.single_box_labels.map((label) => (
      normalizeBoxLabel(label) === oldKey ? newLabel : label
    )),
    mixed_box_groups: pallet.mixed_box_groups.map((group) => group.map((label) => (
      normalizeBoxLabel(label) === oldKey ? newLabel : label
    ))),
    reference_box_label: normalizeBoxLabel(pallet.reference_box_label) === oldKey
      ? newLabel : pallet.reference_box_label,
  }));
}
