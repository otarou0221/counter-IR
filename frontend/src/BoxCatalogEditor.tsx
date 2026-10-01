import type { BoxClassSpec } from "./types";
import { createBoxClassSpec, normalizeBoxLabel } from "./boxCatalog";
import { boxFieldErrors } from "./boxValidation";
import { fieldChanged } from "./changeTracking";
import SettingsNumberField from "./SettingsNumberField";
import SettingsTextField from "./SettingsTextField";
import { settingsFieldId, settingsSectionIds } from "./settingsFieldIds";

type Props = {
  catalog: BoxClassSpec[];
  savedCatalog: BoxClassSpec[];
  selectedLabels: Set<string>;
  onCatalogChange: (value: BoxClassSpec[], renamed?: { oldLabel: string; newLabel: string }) => void;
};

export default function BoxCatalogEditor(props: Props) {
  const change = (index: number, patch: Partial<BoxClassSpec>) => {
    const oldLabel = props.catalog[index].label;
    const updated = props.catalog.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item);
    props.onCatalogChange(updated, patch.label === undefined ? undefined : { oldLabel, newLabel: patch.label });
  };
  return <section className="box-catalog" id={settingsSectionIds.boxes} tabIndex={-1}>
    <div className="config-heading"><h3>共通箱カタログ</h3>
      <button type="button"
        onClick={() => props.onCatalogChange([...props.catalog, createBoxClassSpec(props.catalog)])}>
        ＋ 箱を追加
      </button></div>
    <p>箱名と外寸をDBで一元管理します。</p>
    <div className="box-catalog-list">{props.catalog.map((box, index) => {
      const normalized = normalizeBoxLabel(box.label);
      const selected = props.selectedLabels.has(normalized);
      const errors = boxFieldErrors(box, props.catalog);
      const configured = Object.keys(errors).length === 0;
      const saved = props.savedCatalog[index];
      return <div className="box-class" key={index}>
        <div className="box-class-heading"><strong>箱クラス {index + 1}</strong>
          <button type="button" disabled={selected || props.catalog.length === 1}
            title={selected ? "パレットの対象から外してから削除してください" : "削除"}
            onClick={() => props.onCatalogChange(props.catalog.filter((_item, itemIndex) => itemIndex !== index))}>削除</button></div>
        <SettingsTextField id={settingsFieldId.box(index, "label")}
          label="箱名" value={box.label} required error={errors.label}
          changed={fieldChanged(box, saved, "label")}
          onChange={(label) => change(index, { label })} />
        <div className="box-dimensions">
          <SettingsNumberField id={settingsFieldId.box(index, "width_mm")}
            label="幅(mm)" value={box.width_mm} min={1} error={errors.width_mm}
            changed={fieldChanged(box, saved, "width_mm")}
            onChange={(width_mm) => change(index, { width_mm })} />
          <SettingsNumberField id={settingsFieldId.box(index, "depth_mm")}
            label="奥行(mm)" value={box.depth_mm} min={1} error={errors.depth_mm}
            changed={fieldChanged(box, saved, "depth_mm")}
            onChange={(depth_mm) => change(index, { depth_mm })} />
          <SettingsNumberField id={settingsFieldId.box(index, "height_mm")}
            label="高さ(mm)" value={box.height_mm} min={1} error={errors.height_mm}
            changed={fieldChanged(box, saved, "height_mm")}
            onChange={(height_mm) => change(index, { height_mm })} />
        </div>
        {!configured && <p className="input-error">この箱の必須項目を修正してください。</p>}
      </div>;
    })}</div>
  </section>;
}
