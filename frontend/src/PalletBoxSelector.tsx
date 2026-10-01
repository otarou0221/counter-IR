import { boxRuleLabels, normalizeBoxLabel } from "./boxCatalog";
import MixedBoxGroupEditor from "./MixedBoxGroupEditor";
import type { BoxClassSpec, PalletSettings } from "./types";
import SettingsFieldLabel from "./SettingsFieldLabel";

type Props = {
  pallet: PalletSettings;
  catalog: BoxClassSpec[];
  onChange: (patch: Partial<PalletSettings>) => void;
};

export default function PalletBoxSelector({ pallet, catalog, onChange }: Props) {
  const singles = new Set(pallet.single_box_labels.map(normalizeBoxLabel));
  const configuredCatalog = catalog.filter((box) => (
    box.width_mm > 0 && box.depth_mm > 0 && box.height_mm > 0
  ));
  const updateRules = (singleBoxLabels: string[], mixedBoxGroups: string[][]) => {
    const candidate = {
      ...pallet,
      single_box_labels: singleBoxLabels,
      mixed_box_groups: mixedBoxGroups,
    };
    const labels = boxRuleLabels(candidate);
    const referenceStillSelected = labels.some((label) => (
      normalizeBoxLabel(label) === normalizeBoxLabel(pallet.reference_box_label)
    ));
    onChange({
      single_box_labels: singleBoxLabels,
      mixed_box_groups: mixedBoxGroups,
      reference_box_label: referenceStillSelected
        ? pallet.reference_box_label
        : labels[0] ?? "",
    });
  };
  const toggleSingle = (label: string, checked: boolean) => {
    const next = checked
      ? [...pallet.single_box_labels.filter((item) => normalizeBoxLabel(item) !== normalizeBoxLabel(label)), label]
      : pallet.single_box_labels.filter((item) => normalizeBoxLabel(item) !== normalizeBoxLabel(label));
    updateRules(next, pallet.mixed_box_groups);
  };
  const ruleLabels = boxRuleLabels(pallet);

  return <div className="pallet-box-selector">
    <h4><SettingsFieldLabel label="単品で置かれる箱" required /></h4>
    <p className="settings-help">同じ種類の箱だけでパレットへ置かれる可能性がある箱を選択します。</p>
    <div className="class-options">{catalog.map((box) => {
      const checked = singles.has(normalizeBoxLabel(box.label));
      const configured = configuredCatalog.includes(box);
      return <label key={box.label} className="checkbox-field"><input type="checkbox"
        checked={checked} disabled={!configured}
        onChange={(event) => toggleSingle(box.label, event.target.checked)} />{box.label}
        {!configured && "（寸法未入力）"}</label>;
    })}</div>

    <MixedBoxGroupEditor catalog={configuredCatalog} groups={pallet.mixed_box_groups}
      onChange={(groups) => updateRules(pallet.single_box_labels, groups)} />

    <h4><SettingsFieldLabel label="高さ・局所突起判定の基準箱" required /></h4>
    <div className="class-options">{ruleLabels.map((label) => <label key={label} className="checkbox-field">
      <input type="radio" name={`reference-box-${pallet.pallet_id}`} value={label}
        checked={normalizeBoxLabel(pallet.reference_box_label) === normalizeBoxLabel(label)}
        onChange={() => onChange({ reference_box_label: label })} />{label}</label>)}</div>
  </div>;
}
