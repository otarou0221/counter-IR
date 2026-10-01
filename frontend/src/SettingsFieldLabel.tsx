export default function SettingsFieldLabel({ label, required, managed = false }: {
  label: string;
  required?: boolean;
  managed?: boolean;
}) {
  return <span className="settings-field-label">
    {label}
    <small className={managed ? "managed-label" : required ? "required-label" : "optional-label"}>
      {managed ? "自動管理" : required ? "必須" : "任意"}
    </small>
  </span>;
}
