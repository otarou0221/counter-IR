import { createCameraSettings } from "./cameraSettings";
import { cameraFieldErrors } from "./cameraValidation";
import { fieldChanged } from "./changeTracking";
import Ipv4AddressField from "./Ipv4AddressField";
import SettingsNumberField from "./SettingsNumberField";
import SettingsTextField from "./SettingsTextField";
import { settingsFieldId, settingsSectionIds } from "./settingsFieldIds";
import { createPalletPair } from "./palletLayout";
import type { CameraSettings, PalletSettings } from "./types";

type Props = {
  cameras: CameraSettings[];
  savedCameras: CameraSettings[];
  pallets: PalletSettings[];
  selectedCameraId: string;
  onSelect: (cameraId: string) => void;
  onChange: (cameras: CameraSettings[], pallets: PalletSettings[]) => void;
};

export default function CameraSettingsEditor({ cameras, savedCameras, pallets,
  selectedCameraId, onSelect, onChange }: Props) {
  const selected = cameras.find((camera) => camera.camera_id === selectedCameraId) ?? cameras[0];
  if (!selected) return null;
  const saved = savedCameras.find((camera) => camera.camera_id === selected.camera_id);
  const changed = <Key extends keyof CameraSettings>(key: Key) => fieldChanged(selected, saved, key);
  const errors = cameraFieldErrors(selected);
  const incompleteCameras = cameras.filter((camera) => Object.keys(cameraFieldErrors(camera)).length > 0);
  const update = (patch: Partial<CameraSettings>) => onChange(
    cameras.map((camera) => camera.camera_id === selected.camera_id ? { ...camera, ...patch } : camera),
    pallets,
  );
  const add = () => {
    const camera = createCameraSettings(cameras);
    onChange([...cameras, camera], [...pallets, ...createPalletPair(camera.camera_id, pallets)]);
    onSelect(camera.camera_id);
  };
  const remove = () => {
    if (!window.confirm(`${selected.display_name}と所属するパレット設定を削除します。よろしいですか？`)) return;
    const remaining = cameras.filter((camera) => camera.camera_id !== selected.camera_id);
    onChange(remaining, pallets.filter((pallet) => pallet.camera_id !== selected.camera_id));
    onSelect(remaining[0]?.camera_id ?? "");
  };
  return <section className="camera-settings" id={settingsSectionIds.cameras} tabIndex={-1}>
    <div className="config-heading"><h3>カメラ設定</h3>
      <button type="button" onClick={add}>＋ カメラを追加</button></div>
    <p>画面上部で選択した1台を設定しています。登録数: {cameras.length}台</p>
    <article className="camera-setting">
      <div className="box-class-heading"><strong>{selected.display_name}</strong>
        <code>{selected.camera_id}</code>
        <button type="button" disabled={cameras.length === 1}
          title="カメラと所属するパレット2枠を削除"
          onClick={remove}>このカメラを削除</button></div>
      <div className="settings-grid camera-connection-grid">
        <SettingsTextField id={settingsFieldId.camera(selected.camera_id, "display_name")}
          label="表示名" value={selected.display_name} required
          changed={changed("display_name")}
          error={errors.display_name} onChange={(display_name) => update({ display_name })} />
        <SettingsTextField id={settingsFieldId.camera(selected.camera_id, "camera_code")}
          label="カメラ管理コード" value={selected.camera_code} required
          changed={changed("camera_code")}
          error={errors.camera_code} onChange={(camera_code) => update({ camera_code })} />
        <Ipv4AddressField id={settingsFieldId.camera(selected.camera_id, "ip")}
          label="接続先IP" value={selected.ip}
          changed={changed("ip")}
          error={errors.ip} onChange={(ip) => update({ ip })} />
        <SettingsNumberField id={settingsFieldId.camera(selected.camera_id, "port")}
          label="接続先ポート" value={selected.port}
          changed={changed("port")}
          min={1} max={65535} error={errors.port} onChange={(port) => update({ port })} />
      </div>
      <section className="camera-advanced-settings camera-equipment-settings">
        <h4>カメラ機器情報</h4>
        <div className="settings-grid">
          <SettingsTextField label="メーカー" value={selected.manufacturer ?? ""}
            changed={changed("manufacturer")}
            onChange={(value) => update({ manufacturer: optionalText(value) })} />
          <SettingsTextField label="機種名" value={selected.model_name ?? ""}
            changed={changed("model_name")}
            onChange={(value) => update({ model_name: optionalText(value) })} />
          <SettingsTextField label="製造番号" value={selected.serial_number ?? ""}
            changed={changed("serial_number")}
            onChange={(value) => update({ serial_number: optionalText(value) })} />
        </div>
      </section>
      <details className="camera-advanced-settings" open><summary>設置場所の設定</summary>
        <div className="settings-grid">
          <SettingsTextField label="場所ID" value={selected.location_id?.toString() ?? "保存時に自動採番"} readOnly />
          <SettingsTextField id={settingsFieldId.camera(selected.camera_id, "factory_name")}
            label="工場名" value={selected.factory_name ?? ""} required
            changed={changed("factory_name")}
            error={errors.factory_name} onChange={(value) => update({ factory_name: optionalText(value) })} />
          <SettingsTextField id={settingsFieldId.camera(selected.camera_id, "building_name")}
            label="建物・工場棟名" value={selected.building_name ?? ""} required
            changed={changed("building_name")}
            error={errors.building_name} onChange={(value) => update({ building_name: optionalText(value) })} />
          <SettingsTextField id={settingsFieldId.camera(selected.camera_id, "floor_name")}
            label="フロア名" value={selected.floor_name ?? ""} required
            changed={changed("floor_name")}
            error={errors.floor_name} onChange={(value) => update({ floor_name: optionalText(value) })} />
          <SettingsTextField label="エリア名" value={selected.area_name ?? ""}
            changed={changed("area_name")}
            placeholder="任意（例: 検査課、資材置場）"
            onChange={(value) => update({ area_name: optionalText(value) })} />
          <SettingsTextField label="取付メモ" value={selected.mounting_note ?? ""}
            changed={changed("mounting_note")}
            onChange={(value) => update({ mounting_note: optionalText(value) })} />
        </div>
        <small>場所IDは設定保存時にDBが自動採番し、作成後は変更できません。</small>
      </details>
      {incompleteCameras.length > 0 && <p className="input-error">
        必須項目が未入力のカメラ: {incompleteCameras.map((camera) => camera.display_name || camera.camera_id).join(", ")}
      </p>}
    </article>
  </section>;
}

function optionalText(value: string): string | null {
  return value.trim() === "" ? null : value;
}
