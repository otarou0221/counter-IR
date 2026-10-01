import { useId, type ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  disabledReason?: string;
};

export default function ActionButton({ disabledReason, disabled, title, children,
  ...buttonProps }: Props) {
  const reasonId = useId();
  const unavailable = disabled || Boolean(disabledReason);
  return <>
    <button {...buttonProps} disabled={unavailable}
      title={unavailable ? disabledReason ?? title : title}
      aria-describedby={disabledReason ? reasonId : buttonProps["aria-describedby"]}>
      {children}
    </button>
    {disabledReason && <span className="visually-hidden" id={reasonId}>{disabledReason}</span>}
  </>;
}
