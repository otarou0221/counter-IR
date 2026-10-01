"""例外をUIから再利用できる運用問題へ変換する。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from cardboard_counter_v2.common.operational_issues import (
    IssueActionTarget,
    IssueCategory,
    OperationalIssue,
)


@dataclass(frozen=True)
class IssueRule:
    fragments: tuple[str, ...]
    category: IssueCategory
    title: str
    cause: str
    action: str
    action_target: IssueActionTarget


# ルールは監視周期ごとに作らず、プロセス起動時に一度だけ生成する。
ISSUE_RULES = (
    IssueRule(
        fragments=("床画像", "校正id", "校正定義", "有効パレット校正", "roi"),
        category="calibration",
        title="{camera}の測定準備が完了していません",
        cause="床画像またはパレット校正の設定が不足しています。",
        action="設定画面で床画像とROIを確認し、床基準校正を実行してください。",
        action_target="settings",
    ),
    IssueRule(
        fragments=("orbbec", "フレーム", "timed out", "timeout", "offline", "接続でき"),
        category="camera_connection",
        title="{camera}の撮影に失敗しました",
        cause="カメラから画像を取得できませんでした。",
        action="カメラの電源・LAN接続を確認し、Orbbec Viewerなどカメラを使用するアプリを閉じてください。",
        action_target="field_camera",
    ),
    IssueRule(
        fragments=("db", "データベース", "台帳", "保存に失敗", "保存できません"),
        category="storage",
        title="測定履歴を保存できませんでした",
        cause="測定結果または撮影履歴をデータベースへ保存できませんでした。",
        action="保守・診断画面でサービスとデータベースの状態を確認してください。",
        action_target="debug",
    ),
    IssueRule(
        fragments=("測定ランタイム", "解析", "点群", "measurement"),
        category="measurement",
        title="{camera}の測定処理に失敗しました",
        cause="撮影画像の解析処理を完了できませんでした。",
        action="保守・診断画面で撮影データと測定サービスの状態を確認してください。",
        action_target="debug",
    ),
)


def issue_from_measurement_error(
    error: Exception,
    *,
    camera_id: str,
    occurred_at: str,
) -> OperationalIssue:
    detail = error_detail(error)
    normalized = detail.casefold()
    rule = next(
        (item for item in ISSUE_RULES if any(fragment in normalized for fragment in item.fragments)),
        None,
    )
    camera = camera_id or "カメラ"
    if rule is None:
        return OperationalIssue(
            category="system",
            title=f"{camera}の監視処理に失敗しました",
            cause="監視処理中に予期しない問題が発生しました。",
            action="技術的な詳細を確認し、解消しない場合は保守・診断画面を確認してください。",
            technical_detail=detail,
            occurred_at=occurred_at,
            camera_id=camera_id or None,
            action_target="debug",
        )
    return OperationalIssue(
        category=rule.category,
        title=rule.title.format(camera=camera),
        cause=rule.cause,
        action=rule.action,
        technical_detail=detail,
        occurred_at=occurred_at,
        camera_id=camera_id or None,
        action_target=rule.action_target,
    )


def issue_from_monitor_error(error: Exception, *, occurred_at: str) -> OperationalIssue:
    return OperationalIssue(
        category="system",
        title="監視処理を完了できませんでした",
        cause="監視全体の処理中に予期しない問題が発生しました。",
        action="技術的な詳細と保守・診断画面のサービス状態を確認してください。",
        technical_detail=error_detail(error),
        occurred_at=occurred_at,
        action_target="debug",
    )


def issue_from_email_error(error: Exception, *, occurred_at: str) -> OperationalIssue:
    return OperationalIssue(
        category="notification",
        title="低在庫メールを送信できませんでした",
        cause="SMTPサーバーへの接続またはメール送信に失敗しました。",
        action="設定画面でメール設定を確認してください。監視と測定は継続します。",
        technical_detail=error_detail(error),
        occurred_at=occurred_at,
        action_target="settings",
    )


def error_detail(error: Exception) -> str:
    return str(error.detail) if isinstance(error, HTTPException) else str(error)
