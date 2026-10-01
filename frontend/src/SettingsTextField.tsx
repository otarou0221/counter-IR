import { useId } from "react";
import SettingsFieldLabel from "./SettingsFieldLabel";
import SettingsFieldMessage from "./SettingsFieldMessage";

export default function SettingsTextField({ id, label, value, required = false, readOnly = false,
  placeholder, error, changed = false, onChange }: {
  label: string;
  id?: string;
  value: string;
  required?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  error?: string;
  changed?: boolean;
  onChange?: (value: string) => void;
}) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return <label className={`settings-field ${changed ? "changed" : ""}`}>
    <SettingsFieldLabel label={label} required={required} managed={readOnly} />
    <input id={inputId} value={value} required={required} readOnly={readOnly}
      aria-invalid={Boolean(error)} aria-describedby={error ? `${inputId}-error` : undefined}
      placeholder={placeholder} onChange={(event) => onChange?.(event.target.value)} />
    <SettingsFieldMessage inputId={inputId} error={error} />
  </label>;
}
