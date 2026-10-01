from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from cardboard_counter_v2.api.monitoring import MonitorController, annotate_low_stock
from cardboard_counter_v2.api.notifications import LowStockEmailTracker, SmtpSettings
from cardboard_counter_v2.common.schemas import (
    CameraMeasurementRun,
    MeasurementResponse,
    PalletMeasurement,
    SystemSettings,
)


def measurement(volume_liters: float) -> MeasurementResponse:
    return MeasurementResponse(
        measurement_id=f"measurement_{volume_liters}",
        camera_runs=[CameraMeasurementRun(
            camera_id="camera_1",
            measurement_id=f"measurement_{volume_liters}",
            calibration_id="calibration_1",
            baseline_capture_id="floor_1",
            current_capture_id=f"current_{volume_liters}",
        )],
        pallets=[PalletMeasurement(
            pallet_id=1,
            pallet_number=1,
            camera_id="camera_1",
            volume_liters=volume_liters,
            estimated_boxes=1,
            occupied_cells=1,
            observed_cells=1,
            plane_rmse_mm=1,
            protrusion_components=0,
            protrusion_cells=0,
            protrusion_volume_liters=0,
        )],
    )


def test_low_stock_email_requires_recovery_and_new_threshold_crossing() -> None:
    settings = SystemSettings()
    tracker = LowStockEmailTracker()

    assert tracker.evaluate(measurement(4), settings) == []
    assert tracker.evaluate(measurement(4), settings) == []
    assert tracker.evaluate(measurement(158), settings) == []
    assert tracker.evaluate(measurement(159), settings) == []
    alerts = tracker.evaluate(measurement(5), settings)
    assert [alert.pallet_id for alert in alerts] == [1]

    tracker.mark_sent(1)
    assert tracker.evaluate(measurement(4), settings) == []
    assert tracker.evaluate(measurement(159), settings) == []
    assert [alert.pallet_id for alert in tracker.evaluate(measurement(5), settings)] == [1]


def test_monitor_sends_once_and_records_timestamp(monkeypatch) -> None:
    settings = SystemSettings()
    sent = []
    recorded = []

    async def run_inline(operation, *args, **kwargs):
        return operation(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_inline)

    class Store:
        def load(self):
            return settings

    class Notifier:
        enabled = True

        def send(self, alert):
            sent.append(alert)

    class History:
        def mark_email_sent(self, **values):
            recorded.append(values)
            return True

    monitor = MonitorController(
        store=Store(),  # type: ignore[arg-type]
        workflow=object(),  # type: ignore[arg-type]
        operation_lock=asyncio.Lock(),
        history=History(),  # type: ignore[arg-type]
        notifier=Notifier(),  # type: ignore[arg-type]
    )
    finished_at = datetime(2026, 8, 25, tzinfo=UTC)

    async def run_scenario() -> None:
        await monitor._send_low_stock_alerts(  # noqa: SLF001
            measurement(100), settings, finished_at=finished_at
        )
        await monitor._send_low_stock_alerts(  # noqa: SLF001
            measurement(5), settings, finished_at=finished_at
        )
        await monitor._send_low_stock_alerts(  # noqa: SLF001
            measurement(4), settings, finished_at=finished_at
        )
        await monitor.shutdown()

    asyncio.run(run_scenario())

    assert len(sent) == 1
    assert recorded[0]["calibration_id"] == "calibration_1"
    assert recorded[0]["pallet_number"] == 1
    assert monitor.status.last_email_sent_at is not None
    assert monitor.status.last_email_error is None


def test_low_stock_annotation_is_in_api_layer() -> None:
    result = annotate_low_stock(measurement(5), SystemSettings())
    assert result.pallets[0].is_low_stock is True
    assert result.pallets[0].low_stock_threshold_liters == 5


def test_smtp_settings_are_disabled_until_required_values_exist(monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.delenv("LOW_STOCK_EMAIL_TO", raising=False)
    assert SmtpSettings.from_environment() is None

    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "counter@example.test")
    monkeypatch.setenv("LOW_STOCK_EMAIL_TO", "stock@example.test, boss@example.test")
    configured = SmtpSettings.from_environment()
    assert configured is not None
    assert configured.recipients == (
        "stock@example.test", "boss@example.test"
    )
