import { useId } from "react";
import SettingsFieldLabel from "./SettingsFieldLabel";
import SettingsFieldMessage from "./SettingsFieldMessage";

export default function SettingsNumberField({ id, label, value, min, max, step = 1,
  error, changed = false, onChange }: {
  label: string;
  id?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number | "any";
  error?: string;
  changed?: boolean;
  onChange: (value: number) => void;
}) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return <label className={`settings-field ${changed ? "changed" : ""}`}>
    <SettingsFieldLabel label={label} required />
    <input id={inputId} type="number" value={Number.isFinite(value) ? value : ""}
      min={min} max={max} step={step} required aria-invalid={Boolean(error)}
      aria-describedby={error ? `${inputId}-error` : undefined}
      onChange={(event) => onChange(event.target.value === "" ? Number.NaN : Number(event.target.value))} />
    <SettingsFieldMessage inputId={inputId} error={error} />
  </label>;
}
