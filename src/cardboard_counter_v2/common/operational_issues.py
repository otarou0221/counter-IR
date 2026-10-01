"""画面や通知方法に依存しない、運用上の問題を表す共通契約。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


IssueCategory = Literal[
    "camera_connection",
    "calibration",
    "storage",
    "measurement",
    "notification",
    "system",
]
IssueActionTarget = Literal["field_camera", "settings", "debug"]


class OperationalIssue(BaseModel):
    """利用者向け説明と保守向け詳細を分離したエラー情報。"""

    category: IssueCategory
    title: str
    cause: str
    action: str
    technical_detail: str
    occurred_at: str
    camera_id: str | None = None
    action_target: IssueActionTarget | None = None
