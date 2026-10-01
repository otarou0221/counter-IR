import ActionButton from "./ActionButton";
import MonitorPanel from "./MonitorPanel";
import type { MonitorStatus, OperationalIssue } from "./types";
import type { UiNotice } from "./uiNotice";

type Props = {
  busy: boolean;
  dirty: boolean;
  startDisabled: boolean;
  monitor: MonitorStatus;
  notice: UiNotice;
  onStart: () => void;
  onStop: () => void;
  onIssueAction: (issue: OperationalIssue) => void;
};

export default function SystemStatusBar({ busy, dirty, startDisabled, monitor, notice,
  onStart, onStop, onIssueAction }: Props) {
  const monitorLabel = monitor.stopping ? "停止処理中" : monitor.running ? "常時監視中" : "監視停止中";
  const startReason = busy ? "別の処理が完了するまで監視を開始できません"
    : monitor.running ? "常時監視はすでに実行中です"
      : dirty ? "未保存の設定を保存してください"
        : startDisabled ? "設定の読込みまたは入力エラーの修正が必要です" : undefined;
  const stopReason = busy ? "別の処理が完了するまで監視を停止できません"
    : monitor.stopping ? "監視の停止処理を実行中です"
      : !monitor.running ? "常時監視はすでに停止しています" : undefined;
  return <section className="system-status-bar" aria-label="システム状態">
    <div className={`system-monitor-state ${monitor.running ? "active" : ""}`}>
      <span className="monitor-light" aria-hidden="true" />
      <strong>{monitorLabel}</strong>
      {dirty && <span className="system-dirty-badge">未保存設定あり</span>}
    </div>
    <p className={`system-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}
      aria-live="polite">{busy && <span className="busy-indicator" aria-hidden="true" />}{notice.message}</p>
    <div className="system-monitor-actions-wrap">
      <div className="system-monitor-actions">
        <ActionButton className="monitor-start" disabledReason={startReason}
          onClick={onStart}>{monitor.running ? "監視中" : "監視開始"}</ActionButton>
        <ActionButton className="monitor-stop" disabledReason={stopReason}
          onClick={onStop}>{monitor.running ? "監視停止" : "停止済み"}</ActionButton>
      </div>
      {!monitor.running && startReason && !busy && <small>{startReason}</small>}
    </div>
    <details className="system-status-details">
      <summary>監視詳細</summary>
      <MonitorPanel monitor={monitor} onIssueAction={onIssueAction} />
    </details>
  </section>;
}
