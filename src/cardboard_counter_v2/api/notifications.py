"""低在庫メールの状態遷移とSMTP境界。"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib
from typing import Protocol

from cardboard_counter_v2.common.schemas import MeasurementResponse, SystemSettings
from cardboard_counter_v2.api.inventory.domain import evaluate_low_stock


@dataclass(frozen=True)
class LowStockAlert:
    pallet_id: int
    pallet_number: int
    camera_id: str
    display_name: str
    volume_liters: float
    threshold_liters: float


class LowStockNotifier(Protocol):
    @property
    def enabled(self) -> bool: ...

    def send(self, alert: LowStockAlert) -> None: ...


class LowStockEmailTracker:
    """監視開始からの回復・低下だけを追跡する。"""

    def __init__(self) -> None:
        self._armed: dict[int, bool] = {}
        self._pending: set[int] = set()

    def reset(self) -> None:
        self._armed.clear()
        self._pending.clear()

    def evaluate(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
    ) -> list[LowStockAlert]:
        configured = {pallet.pallet_id: pallet for pallet in settings.pallets}
        alerts: list[LowStockAlert] = []
        for measured in result.pallets:
            pallet = configured.get(measured.pallet_id)
            if pallet is None or not pallet.enabled:
                continue
            volume = max(float(measured.volume_liters), 0.0)
            threshold = pallet.low_stock_threshold_liters
            is_low_stock = evaluate_low_stock(volume, threshold).is_low_stock
            armed = self._armed.get(pallet.pallet_id)
            if armed is None:
                # 監視開始時から低在庫なら送信せず、回復するまで無効にする。
                self._armed[pallet.pallet_id] = not is_low_stock
                continue
            if not armed:
                if volume >= threshold + pallet.email_rearm_margin_liters:
                    self._armed[pallet.pallet_id] = True
                continue
            if pallet.pallet_id in self._pending:
                continue
            if is_low_stock:
                alerts.append(LowStockAlert(
                    pallet_id=pallet.pallet_id,
                    pallet_number=pallet.pallet_number,
                    camera_id=pallet.camera_id,
                    display_name=pallet.display_name,
                    volume_liters=volume,
                    threshold_liters=threshold,
                ))
        return alerts

    def mark_queued(self, pallet_id: int) -> None:
        self._pending.add(pallet_id)

    def mark_sent(self, pallet_id: int) -> None:
        self._pending.discard(pallet_id)
        self._armed[pallet_id] = False

    def mark_failed(self, pallet_id: int) -> None:
        self._pending.discard(pallet_id)


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None = None
    password: str | None = None
    security: str = "starttls"
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "SmtpSettings | None":
        host = os.environ.get("SMTP_HOST", "").strip()
        sender = os.environ.get("SMTP_FROM", "").strip()
        recipients = tuple(
            value.strip()
            for value in os.environ.get("LOW_STOCK_EMAIL_TO", "").split(",")
            if value.strip()
        )
        if not host or not sender or not recipients:
            return None
        security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
        if security not in {"starttls", "ssl", "none"}:
            raise ValueError("SMTP_SECURITYはstarttls・ssl・noneのいずれかです")
        username = os.environ.get("SMTP_USERNAME", "").strip() or None
        password = os.environ.get("SMTP_PASSWORD", "") or None
        if bool(username) != bool(password):
            raise ValueError("SMTP_USERNAMEとSMTP_PASSWORDは両方設定してください")
        default_port = 465 if security == "ssl" else 587
        return cls(
            host=host,
            port=int(os.environ.get("SMTP_PORT", str(default_port))),
            sender=sender,
            recipients=recipients,
            username=username,
            password=password,
            security=security,
            timeout_seconds=float(os.environ.get("SMTP_TIMEOUT_SECONDS", "10")),
        )


class SmtpLowStockNotifier:
    def __init__(self, settings: SmtpSettings | None) -> None:
        self.settings = settings

    @classmethod
    def from_environment(cls) -> "SmtpLowStockNotifier":
        return cls(SmtpSettings.from_environment())

    @property
    def enabled(self) -> bool:
        return self.settings is not None

    def send(self, alert: LowStockAlert) -> None:
        settings = self.settings
        if settings is None:
            raise RuntimeError("低在庫メールのSMTP設定がありません")
        message = EmailMessage()
        message["From"] = settings.sender
        message["To"] = ", ".join(settings.recipients)
        message["Subject"] = (
            f"【低在庫】{alert.display_name}（{alert.camera_id}）"
        )
        message.set_content(
            "パレットの残体積が警告しきい値以下になりました。\n\n"
            f"カメラ: {alert.camera_id}\n"
            f"パレット: {alert.display_name}（番号{alert.pallet_number}）\n"
            f"現在体積: {alert.volume_liters:.3f} L\n"
            f"警告しきい値: {alert.threshold_liters:.3f} L\n"
        )
        smtp_type = smtplib.SMTP_SSL if settings.security == "ssl" else smtplib.SMTP
        with smtp_type(
            settings.host,
            settings.port,
            timeout=settings.timeout_seconds,
        ) as client:
            if settings.security == "starttls":
                client.starttls()
            if settings.username is not None and settings.password is not None:
                client.login(settings.username, settings.password)
            client.send_message(message)
