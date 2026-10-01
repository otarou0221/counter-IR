"""設定更新時にだけ適用する、管理情報と不変IDの検証。"""

from __future__ import annotations

from cardboard_counter_v2.common.schemas import SystemSettings


REQUIRED_CAMERA_FIELDS = (
    ("display_name", "表示名"),
    ("camera_code", "カメラ管理コード"),
    ("ip", "接続先IP"),
    ("factory_name", "工場名"),
    ("building_name", "建物・工場棟名"),
    ("floor_name", "フロア名"),
)


def validate_camera_settings_update(
    previous: SystemSettings,
    current: SystemSettings,
) -> None:
    """保存必須項目と、既存場所IDが変更されていないことを確認する。"""
    for camera in current.cameras:
        missing = [
            label
            for field_name, label in REQUIRED_CAMERA_FIELDS
            if not _text(getattr(camera, field_name))
        ]
        if missing:
            raise ValueError(
                f"{camera.camera_id}の必須項目を入力してください: {', '.join(missing)}"
            )

    previous_by_id = {camera.camera_id: camera for camera in previous.cameras}
    for camera in current.cameras:
        old = previous_by_id.get(camera.camera_id)
        if old is not None and camera.location_id != old.location_id:
            raise ValueError(
                f"{camera.camera_id}の場所IDは作成後に変更できません"
            )
        if old is None and camera.location_id is not None:
            raise ValueError(
                f"{camera.camera_id}の場所IDはDBの自動採番を使用してください"
            )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
