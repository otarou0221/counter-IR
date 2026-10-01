from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from cardboard_counter_v2.api.issue_reporting import (
    issue_from_email_error,
    issue_from_measurement_error,
    issue_from_monitor_error,
)


OCCURRED_AT = datetime(2026, 9, 2, tzinfo=UTC).isoformat()


def test_camera_timeout_has_field_action_and_keeps_technical_detail() -> None:
    issue = issue_from_measurement_error(
        RuntimeError("Timed out waiting for an Orbbec frame"),
        camera_id="camera_2",
        occurred_at=OCCURRED_AT,
    )

    assert issue.category == "camera_connection"
    assert issue.title == "camera_2の撮影に失敗しました"
    assert issue.action_target == "field_camera"
    assert issue.technical_detail == "Timed out waiting for an Orbbec frame"


def test_missing_floor_image_has_settings_action() -> None:
    issue = issue_from_measurement_error(
        HTTPException(status_code=409, detail="先に設定画面で床画像を撮影してください"),
        camera_id="camera_1",
        occurred_at=OCCURRED_AT,
    )

    assert issue.category == "calibration"
    assert issue.action_target == "settings"
    assert "床画像" in issue.cause


def test_unknown_monitor_error_has_debug_action() -> None:
    issue = issue_from_monitor_error(
        RuntimeError("unexpected"),
        occurred_at=OCCURRED_AT,
    )

    assert issue.category == "system"
    assert issue.action_target == "debug"
    assert issue.technical_detail == "unexpected"


def test_email_error_explains_monitoring_continues() -> None:
    issue = issue_from_email_error(
        RuntimeError("SMTP unavailable"),
        occurred_at=OCCURRED_AT,
    )

    assert issue.category == "notification"
    assert issue.action_target == "settings"
    assert "継続" in issue.action
