import PalletBoxSelector from "./PalletBoxSelector";
import { palletFieldErrors } from "./palletValidation";
import { fieldChanged, structuredValueChanged } from "./changeTracking";
import SettingsNumberField from "./SettingsNumberField";
import SettingsTextField from "./SettingsTextField";
import { settingsFieldId, settingsSectionIds } from "./settingsFieldIds";
import type { BoxClassSpec, CameraSettings, PalletSettings } from "./types";

type Props = {
  cameras: CameraSettings[];
  selectedCameraId: string;
  pallets: PalletSettings[];
  savedPallets: PalletSettings[];
  catalog: BoxClassSpec[];
  disabled: boolean;
  monitoring: boolean;
  onChange: (pallets: PalletSettings[]) => void;
};

export default function CameraPalletEditor({ cameras, selectedCameraId, pallets, savedPallets, catalog,
  disabled, monitoring, onChange }: Props) {
  const camera = cameras.find((item) => item.camera_id === selectedCameraId);
  if (!camera) return null;
  const visible = pallets.filter((pallet) => pallet.camera_id === selectedCameraId)
    .sort((left, right) => left.pallet_number - right.pallet_number);
  const update = (palletId: number, patch: Partial<PalletSettings>) => onChange(
    pallets.map((pallet) => pallet.pallet_id === palletId ? { ...pallet, ...patch } : pallet),
  );
  return <section className="camera-pallet-settings" id={settingsSectionIds.pallets} tabIndex={-1}>
    <div className="config-heading"><h3>{camera.display_name}のパレットと箱</h3></div>
    <p>各カメラはパレット1・2の2枠固定です。使用しない枠は「測定対象」をオフにします。</p>
    <div className="pallet-settings-grid">{visible.map((pallet) => {
      const change = (patch: Partial<PalletSettings>) => update(pallet.pallet_id, patch);
      const errors = palletFieldErrors(pallet, catalog);
      const saved = savedPallets.find((item) => item.pallet_id === pallet.pallet_id);
      const rulesChanged = !saved
        || structuredValueChanged(pallet.single_box_labels, saved.single_box_labels)
        || structuredValueChanged(pallet.mixed_box_groups, saved.mixed_box_groups)
        || fieldChanged(pallet, saved, "reference_box_label");
      return <article key={pallet.pallet_id}>
        <div className="box-class-heading"><h3>{pallet.display_name}</h3>
          <code>ID {pallet.pallet_id}</code></div>
        <fieldset className="settings-fieldset" disabled={disabled || monitoring}>
          <SettingsTextField id={settingsFieldId.pallet(pallet.pallet_id, "display_name")}
            label="パレット表示名" value={pallet.display_name} required
            changed={fieldChanged(pallet, saved, "display_name")}
            error={errors.display_name} onChange={(display_name) => change({ display_name })} />
        </fieldset>
        <fieldset className="settings-fieldset" disabled={disabled}>
          <SettingsNumberField id={settingsFieldId.pallet(pallet.pallet_id, "low_stock_threshold_liters")}
            label="低在庫警告体積(L)" value={pallet.low_stock_threshold_liters}
            changed={fieldChanged(pallet, saved, "low_stock_threshold_liters")}
            min={1} step="any" error={errors.low_stock_threshold_liters}
            onChange={(low_stock_threshold_liters) => change({ low_stock_threshold_liters })} />
          <SettingsNumberField id={settingsFieldId.pallet(pallet.pallet_id, "email_rearm_margin_liters")}
            label="メール再有効化増加量(L)" value={pallet.email_rearm_margin_liters}
            changed={fieldChanged(pallet, saved, "email_rearm_margin_liters")}
            min={1} step="any" error={errors.email_rearm_margin_liters}
            onChange={(email_rearm_margin_liters) => change({ email_rearm_margin_liters })} />
        </fieldset>
        <label className={`checkbox-field settings-choice ${fieldChanged(pallet, saved, "enabled") ? "changed" : ""}`}>
          <input id={settingsFieldId.pallet(pallet.pallet_id, "enabled")}
          disabled={disabled || monitoring} type="checkbox" checked={pallet.enabled}
          onChange={(event) => change({ enabled: event.target.checked })} />測定対象</label>
        <fieldset id={settingsFieldId.pallet(pallet.pallet_id, "boxes")} tabIndex={-1}
          className={`settings-fieldset settings-choice ${rulesChanged ? "changed" : ""}`}
          disabled={disabled || monitoring}>
          <PalletBoxSelector pallet={pallet} catalog={catalog} onChange={change} />
        </fieldset>
        {errors.boxes && <p className="input-error">{errors.boxes}</p>}
      </article>;
    })}</div>
  </section>;
}
