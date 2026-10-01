export default function SettingsFieldMessage({ inputId, error }: {
  inputId: string;
  error?: string;
}) {
  return <small id={`${inputId}-error`}
    className={`settings-field-message ${error ? "field-error" : ""}`}
    aria-hidden={!error}>{error ?? "\u00a0"}</small>;
}
