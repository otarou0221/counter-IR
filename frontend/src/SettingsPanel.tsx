import BoxCatalogEditor from "./BoxCatalogEditor";
import CameraPalletEditor from "./CameraPalletEditor";
import CameraSettingsEditor from "./CameraSettingsEditor";
import { fieldChanged } from "./changeTracking";
import { boxRuleLabels, normalizeBoxLabel, renamePalletBoxLabel } from "./boxCatalog";
import { measurementFieldErrors } from "./measurementValidation";
import SettingsNumberField from "./SettingsNumberField";
import { settingsFieldId, settingsSectionIds } from "./settingsFieldIds";
import type { SystemSettings } from "./types";

type Props = {
  settings: SystemSettings | null;
  savedSettings: SystemSettings | null;
  dirty: boolean;
  disabled: boolean;
  monitoring: boolean;
  selectedCameraId: string;
  onCameraChange: (cameraId: string) => void;
  onSettingsChange: (settings: SystemSettings) => void;
};

export default function SettingsPanel({ settings, savedSettings, dirty, disabled, monitoring,
  selectedCameraId, onCameraChange, onSettingsChange }: Props) {
  if (!settings) return <section className="config">設定を読み込み中です。</section>;
  const update = (patch: Partial<SystemSettings>) => onSettingsChange({ ...settings, ...patch });
  const selectedLabels = new Set(settings.pallets.flatMap(boxRuleLabels)
    .map(normalizeBoxLabel));
  const measurementErrors = measurementFieldErrors(settings);
  const changed = <Key extends keyof SystemSettings>(key: Key) => fieldChanged(
    settings,
    savedSettings,
    key,
  );
  const changeCatalog = (box_catalog: SystemSettings["box_catalog"], renamed?: { oldLabel: string; newLabel: string }) => {
    if (!renamed) return update({ box_catalog });
    update({
      box_catalog,
      pallets: renamePalletBoxLabel(settings.pallets, renamed.oldLabel, renamed.newLabel),
    });
  };
  return <section className="config">
    <div className="config-heading"><h2>設備・測定設定</h2>{dirty && <span className="unsaved">未保存</span>}</div>
    <p>カメラ、箱、パレットと測定条件を設定します。</p>
    {monitoring && <p className="warning">監視中は低在庫警告体積とメール再有効化増加量だけ変更できます。</p>}
    <fieldset className="settings-fieldset" disabled={disabled || monitoring}>
      <CameraSettingsEditor cameras={settings.cameras} savedCameras={savedSettings?.cameras ?? []}
        pallets={settings.pallets}
        selectedCameraId={selectedCameraId} onSelect={onCameraChange}
        onChange={(cameras, pallets) => update({ cameras, pallets })} />
      <section className="settings-section" id={settingsSectionIds.measurement} tabIndex={-1}>
        <h3>基本測定設定</h3>
        <div className="settings-grid">
          <SettingsNumberField id={settingsFieldId.measurement("monitor_interval_seconds")}
            label="測定間隔(分)" value={settings.monitor_interval_seconds / 60}
            min={1} max={60} error={measurementErrors.monitor_interval_seconds}
            changed={changed("monitor_interval_seconds")}
            onChange={(minutes) => update({ monitor_interval_seconds: minutes * 60 })} />
          <SettingsNumberField id={settingsFieldId.measurement("pallet_height_mm")}
            label="パレット高さ(mm)" value={settings.pallet_height_mm}
            min={1} max={500} error={measurementErrors.pallet_height_mm}
            changed={changed("pallet_height_mm")}
            onChange={(pallet_height_mm) => update({ pallet_height_mm })} />
        </div>
      </section>
      <BoxCatalogEditor catalog={settings.box_catalog} savedCatalog={savedSettings?.box_catalog ?? []}
        selectedLabels={selectedLabels}
        onCatalogChange={changeCatalog} />
      <details className="settings-advanced">
        <summary>測定処理の詳細設定</summary>
        <p>実験・調整用です。撮影品質や処理負荷を変更する場合だけ使用し、将来の現場画面では非表示にする予定です。</p>
        <div className="settings-grid">
          <SettingsNumberField id={settingsFieldId.measurement("frame_count")}
            label="床校正Depth撮影枚数" value={settings.frame_count} min={3} max={120}
            error={measurementErrors.frame_count}
            changed={changed("frame_count")}
            onChange={(frame_count) => update({ frame_count })} />
          <SettingsNumberField id={settingsFieldId.measurement("measurement_frame_count")}
            label="正式測定Depth撮影枚数" value={settings.measurement_frame_count} min={1} max={120}
            error={measurementErrors.measurement_frame_count}
            changed={changed("measurement_frame_count")}
            onChange={(measurement_frame_count) => update({ measurement_frame_count })} />
          <SettingsNumberField id={settingsFieldId.measurement("measurement_concurrency")}
            label="同時測定カメラ数" value={settings.measurement_concurrency} min={1} max={100}
            error={measurementErrors.measurement_concurrency}
            changed={changed("measurement_concurrency")}
            onChange={(measurement_concurrency) => update({ measurement_concurrency })} />
          <SettingsNumberField id={settingsFieldId.measurement("warmup_frames")}
            label="接続後ウォームアップ枚数" value={settings.warmup_frames} min={0} max={60}
            error={measurementErrors.warmup_frames}
            changed={changed("warmup_frames")}
            onChange={(warmup_frames) => update({ warmup_frames })} />
          <SettingsNumberField id={settingsFieldId.measurement("grid_mm")}
            label="高さグリッド(mm)" value={settings.grid_mm} min={2} max={50} step="any"
            error={measurementErrors.grid_mm}
            changed={changed("grid_mm")}
            onChange={(grid_mm) => update({ grid_mm })} />
          <SettingsNumberField id={settingsFieldId.measurement("occupied_height_mm")}
            label="箱判定最低高さ(mm)" value={settings.occupied_height_mm} min={1} step="any"
            error={measurementErrors.occupied_height_mm}
            changed={changed("occupied_height_mm")}
            onChange={(occupied_height_mm) => update({ occupied_height_mm })} />
        </div>
      </details>
    </fieldset>
    <CameraPalletEditor cameras={settings.cameras} selectedCameraId={selectedCameraId}
      pallets={settings.pallets} savedPallets={savedSettings?.pallets ?? []}
      catalog={settings.box_catalog}
      disabled={disabled} monitoring={monitoring}
      onChange={(pallets) => update({ pallets })} />
  </section>;
}
