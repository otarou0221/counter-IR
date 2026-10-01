import { useId, useRef, type ClipboardEvent, type KeyboardEvent } from "react";
import { isValidIpv4, joinIpv4, normalizeIpv4Octet, splitIpv4 } from "./ipv4";
import SettingsFieldLabel from "./SettingsFieldLabel";
import SettingsFieldMessage from "./SettingsFieldMessage";

type Props = {
  id?: string;
  label: string;
  value: string;
  error?: string;
  changed?: boolean;
  onChange: (value: string) => void;
};

export default function Ipv4AddressField({ id, label, value, error, changed = false, onChange }: Props) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const inputs = useRef<Array<HTMLInputElement | null>>([]);
  const parts = splitIpv4(value);

  const updatePart = (index: number, rawValue: string) => {
    const next = [...parts];
    next[index] = normalizeIpv4Octet(rawValue);
    onChange(joinIpv4(next));
    if ((rawValue.includes(".") || next[index].length === 3) && index < parts.length - 1) {
      inputs.current[index + 1]?.focus();
      inputs.current[index + 1]?.select();
    }
  };

  const moveBetweenParts = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "." && index < parts.length - 1) {
      event.preventDefault();
      inputs.current[index + 1]?.focus();
      inputs.current[index + 1]?.select();
    } else if (event.key === "Backspace" && parts[index] === "" && index > 0) {
      event.preventDefault();
      inputs.current[index - 1]?.focus();
    }
  };

  const pasteAddress = (event: ClipboardEvent<HTMLInputElement>) => {
    const pasted = event.clipboardData.getData("text").trim();
    if (!isValidIpv4(pasted)) return;
    event.preventDefault();
    onChange(pasted);
    inputs.current[3]?.focus();
    inputs.current[3]?.select();
  };

  return <fieldset className={`settings-fieldset settings-field ipv4-field ${changed ? "changed" : ""}`}
    aria-describedby={error ? `${fieldId}-error` : undefined}>
    <legend><SettingsFieldLabel label={label} required /></legend>
    <div className="ipv4-inputs">{parts.map((part, index) => <span className="ipv4-octet" key={index}>
      <input id={index === 0 ? fieldId : `${fieldId}-${index + 1}`}
        ref={(element) => { inputs.current[index] = element; }} value={part}
        inputMode="numeric" pattern="[0-9]*" maxLength={3}
        aria-label={`${label} ${index + 1}番目`} aria-invalid={Boolean(error)}
        onChange={(event) => updatePart(index, event.target.value)}
        onKeyDown={(event) => moveBetweenParts(index, event)} onPaste={pasteAddress} />
      {index < parts.length - 1 && <b aria-hidden="true">.</b>}
    </span>)}</div>
    <SettingsFieldMessage inputId={fieldId} error={error} />
  </fieldset>;
}
