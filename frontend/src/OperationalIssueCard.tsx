import type { OperationalIssue } from "./types";

const actionLabels: Record<NonNullable<OperationalIssue["action_target"]>, string> = {
  field_camera: "現場用で確認",
  settings: "設定画面を開く",
  debug: "保守・診断を開く",
};

type Props = {
  issue: OperationalIssue;
  monitoring: boolean;
  onAction?: (issue: OperationalIssue) => void;
};

export default function OperationalIssueCard({ issue, monitoring, onAction }: Props) {
  return <article className="operational-issue" role="alert">
    <header>
      <strong>{issue.title}</strong>
      {issue.camera_id && <code>{issue.camera_id}</code>}
    </header>
    <dl>
      <div><dt>原因</dt><dd>{issue.cause}</dd></div>
      <div><dt>対応</dt><dd>{issue.action}</dd></div>
    </dl>
    <div className="operational-issue-meta">
      <span>発生日時: {new Date(issue.occurred_at).toLocaleString("ja-JP")}</span>
      <span className={monitoring ? "monitor-continues" : "monitor-stopped"}>
        監視: {monitoring ? "継続中" : "停止中"}
      </span>
    </div>
    {issue.action_target && onAction && <button type="button"
      onClick={() => onAction(issue)}>{actionLabels[issue.action_target]}</button>}
    <details className="operational-issue-technical">
      <summary>技術的な詳細</summary>
      <pre>{issue.technical_detail}</pre>
    </details>
  </article>;
}
