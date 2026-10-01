import OperationalIssueCard from "./OperationalIssueCard";
import type { MonitorStatus, OperationalIssue } from "./types";

const outcomeLabels: Record<MonitorStatus["last_outcome"], string> = {
  not_run: "未実行",
  success: "成功",
  partial_failure: "一部のカメラで失敗",
  failed: "失敗",
};

export default function MonitorPanel({ monitor, onIssueAction }: {
  monitor: MonitorStatus;
  onIssueAction?: (issue: OperationalIssue) => void;
}) {
  const interval = monitor.interval_seconds >= 60
    ? `${monitor.interval_seconds / 60}分`
    : `${monitor.interval_seconds}秒`;
  return <section className={monitor.running ? "monitor active" : "monitor"}>
    <div className="monitor-summary">
      <div><span className="monitor-light" /><strong>{monitor.stopping ? "停止処理中" : monitor.running ? "常時監視中" : "停止中"}</strong></div>
      <dl>
        <div><dt>最終実行結果</dt><dd>{outcomeLabels[monitor.last_outcome ?? "not_run"]}</dd></div>
        <div><dt>成功した監視周期</dt><dd>{monitor.completed_measurements}回</dd></div>
        <div><dt>全カメラ連続失敗</dt><dd>{monitor.consecutive_errors}回</dd></div>
        <div><dt>実行間隔</dt><dd>{interval}</dd></div>
      </dl>
      {monitor.last_finished_at && <p>最終実行: {new Date(monitor.last_finished_at).toLocaleString("ja-JP")}</p>}
      <p>低在庫メール: {monitor.email_notifications_enabled ? "有効" : "SMTP未設定"}</p>
      {monitor.last_email_sent_at && <p>最終メール送信: {new Date(monitor.last_email_sent_at).toLocaleString("ja-JP")}</p>}
    </div>
    <div className="monitor-issues">
      {(monitor.last_issues ?? []).map((issue, index) => <OperationalIssueCard
        key={`${issue.occurred_at}-${issue.camera_id ?? "system"}-${index}`}
        issue={issue} monitoring={monitor.running} onAction={onIssueAction} />)}
      {!monitor.last_issues?.length && monitor.last_error &&
        <p className="monitor-error">測定エラー: {monitor.last_error}</p>}
      {monitor.last_email_issue && <OperationalIssueCard issue={monitor.last_email_issue}
        monitoring={monitor.running} onAction={onIssueAction} />}
      {!monitor.last_email_issue && monitor.last_email_error &&
        <p className="monitor-error">メール送信エラー: {monitor.last_email_error}</p>}
    </div>
  </section>;
}
