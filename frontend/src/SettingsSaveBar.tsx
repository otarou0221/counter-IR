import { useEffect, useState } from "react";
import ActionButton from "./ActionButton";
import type { SettingsValidationIssue } from "./settingsValidation";

export type SettingsSaveState = {
  message: string;
  tone: "saved" | "unsaved" | "blocked";
  disabled: boolean;
};

export function settingsSaveState({ busy, monitoring, dirty, valid, validationMessage }: {
  busy: boolean; monitoring: boolean; dirty: boolean; valid: boolean; validationMessage?: string;
}): SettingsSaveState {
  if (busy) return { message: "処理が完了するまで保存できません", tone: "blocked", disabled: true };
  if (!valid) return { message: validationMessage ?? "未入力・重複・選択内容を修正してください", tone: "blocked", disabled: true };
  if (!dirty) return { message: "設定は保存済みです", tone: "saved", disabled: true };
  if (monitoring) return { message: "警告設定は次回測定から反映されます", tone: "unsaved", disabled: false };
  return { message: "未保存の変更があります", tone: "unsaved", disabled: false };
}

export default function SettingsSaveBar({ busy, monitoring, dirty, valid, validationMessage,
  validationIssues, onIssueSelect, onSave }: {
  busy: boolean; monitoring: boolean; dirty: boolean; valid: boolean;
  validationMessage?: string;
  validationIssues: SettingsValidationIssue[];
  onIssueSelect: (issue: SettingsValidationIssue) => void;
  onSave: () => void;
}) {
  const [errorsOpen, setErrorsOpen] = useState(false);
  useEffect(() => {
    if (validationIssues.length === 0) setErrorsOpen(false);
  }, [validationIssues.length]);
  const state = settingsSaveState({
    busy, monitoring, dirty, valid,
    validationMessage: validationIssues.length
      ? `入力エラーが${validationIssues.length}件あります`
      : validationMessage,
  });
  return <aside className={`settings-save-bar ${state.tone}`} aria-live="polite">
    <div className="settings-save-status">
      <span className="settings-save-message">{state.message}</span>
      {validationIssues.length > 0 && <button type="button" className="settings-error-toggle"
        aria-expanded={errorsOpen} aria-controls="settings-error-list"
        onClick={() => setErrorsOpen((open) => !open)}>エラーを確認</button>}
    </div>
    <ActionButton type="button" className="primary"
      disabledReason={state.disabled ? state.message : undefined} onClick={onSave}>
      {monitoring ? "警告設定を保存" : "設定を保存して校正"}
    </ActionButton>
    {errorsOpen && <section className="settings-error-list" id="settings-error-list"
      aria-label="設定の入力エラー">
      <strong>修正が必要な項目</strong>
      <ol>{validationIssues.map((issue) => <li key={issue.key}>
        <button type="button" onClick={() => {
          setErrorsOpen(false);
          onIssueSelect(issue);
        }}>{issue.message}<span aria-hidden="true">→</span></button>
      </li>)}</ol>
    </section>}
  </aside>;
}
