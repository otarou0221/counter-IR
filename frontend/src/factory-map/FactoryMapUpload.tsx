import { useState } from "react";
import ActionButton from "../ActionButton";
import { api } from "../api";
import type { FactoryMapSummary } from "../types";

type Props = {
  disabled: boolean;
  disabledReason?: string;
  onCreated: (created: FactoryMapSummary) => Promise<void>;
  onError: (message: string) => void;
};

export default function FactoryMapUpload({ disabled, disabledReason, onCreated, onError }: Props) {
  const [displayName, setDisplayName] = useState("");
  const [factoryName, setFactoryName] = useState("");
  const [buildingName, setBuildingName] = useState("");
  const [floorName, setFloorName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const upload = async () => {
    if (!displayName.trim()) throw new Error("マップ表示名を入力してください");
    if (!factoryName.trim()) throw new Error("工場名を入力してください");
    if (!buildingName.trim()) throw new Error("建物・工場棟名を入力してください");
    if (!floorName.trim()) throw new Error("フロア名を入力してください");
    if (!file) throw new Error("PNGファイルを選択してください");
    if (file.type !== "image/png") {
      throw new Error("工場マップはPNG形式で登録してください");
    }
    setErrorMessage(null);
    const query = new URLSearchParams({ display_name: displayName.trim() });
    query.set("factory_name", factoryName.trim());
    query.set("building_name", buildingName.trim());
    query.set("floor_name", floorName.trim());
    setUploading(true);
    try {
      const created = await api<FactoryMapSummary>(`/api/dashboard/maps?${query}`, {
        method: "POST",
        headers: { "Content-Type": "image/png" },
        body: file,
      });
      await onCreated(created);
      setDisplayName("");
      setFactoryName("");
      setBuildingName("");
      setFloorName("");
      setFile(null);
    } finally {
      setUploading(false);
    }
  };

  const reportError = (error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    setErrorMessage(message);
    onError(message);
  };

  return <div className="map-upload-form">
    <label><span className="map-field-label">マップ表示名
      <small className="required-label">必須</small></span>
      <input value={displayName} placeholder="例：第5工場 3階" required
        aria-invalid={Boolean(errorMessage && !displayName.trim())}
        onChange={(event) => {
          setDisplayName(event.target.value);
          setErrorMessage(null);
        }} /></label>
    <label><span className="map-field-label">工場名
      <small className="required-label">必須</small></span>
      <input value={factoryName} placeholder="例：長岡工場" required
      aria-invalid={Boolean(errorMessage && !factoryName.trim())}
      onChange={(event) => {
        setFactoryName(event.target.value);
        setErrorMessage(null);
      }} /></label>
    <label><span className="map-field-label">建物・工場棟名
      <small className="required-label">必須</small></span>
      <input value={buildingName} placeholder="例：第5工場" required
      aria-invalid={Boolean(errorMessage && !buildingName.trim())}
      onChange={(event) => {
        setBuildingName(event.target.value);
        setErrorMessage(null);
      }} /></label>
    <label><span className="map-field-label">フロア名
      <small className="required-label">必須</small></span>
      <input value={floorName} placeholder="例：3階" required
      aria-invalid={Boolean(errorMessage && !floorName.trim())}
      onChange={(event) => {
        setFloorName(event.target.value);
        setErrorMessage(null);
      }} /></label>
    <label><span className="map-field-label">工場マップPNG
      <small className="required-label">必須</small></span>
      <input type="file" accept="image/png" required
        aria-invalid={Boolean(errorMessage && !file)}
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null);
          setErrorMessage(null);
        }} /></label>
    <ActionButton className="primary"
      disabledReason={uploading ? "工場マップを登録中です" : disabled ? disabledReason ?? "現在は登録できません" : undefined}
      onClick={() => {
      void upload().catch(reportError);
    }}>{uploading ? "登録中" : "マップを登録"}</ActionButton>
    {errorMessage && <p className="map-upload-error" role="alert">
      登録できません：{errorMessage}
    </p>}
  </div>;
}
