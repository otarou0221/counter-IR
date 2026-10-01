"""常時監視の状態とバックグラウンドタスクのライフサイクル。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from dataclasses import dataclass

from fastapi import HTTPException

from cardboard_counter_v2.api.inventory.service import InventoryHistoryService
from cardboard_counter_v2.api.inventory.domain import evaluate_low_stock
from cardboard_counter_v2.api.issue_reporting import (
    error_detail,
    issue_from_email_error,
    issue_from_measurement_error,
    issue_from_monitor_error,
)
from cardboard_counter_v2.api.notifications import (
    LowStockAlert,
    LowStockEmailTracker,
    LowStockNotifier,
    SmtpLowStockNotifier,
)
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.api.state import RuntimeState
from cardboard_counter_v2.api.workflows import (
    CameraMeasurementOutcome,
    MeasurementWorkflow,
    combine_measurements,
    format_camera_errors,
)
from cardboard_counter_v2.common.schemas import (
    MeasurementResponse,
    MonitorStatus,
    SystemSettings,
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MonitorController:
    """APIサーバーと同じ期間だけ1つの監視タスクを管理する。"""

    def __init__(
        self,
        *,
        store: SettingsStore,
        workflow: MeasurementWorkflow,
        operation_lock: asyncio.Lock,
        history: InventoryHistoryService | None = None,
        notifier: LowStockNotifier | None = None,
    ) -> None:
        self.store = store
        self.workflow = workflow
        self.operation_lock = operation_lock
        self.history = history
        self.notifier = notifier or SmtpLowStockNotifier(None)
        self.email_tracker = LowStockEmailTracker()
        self.task: asyncio.Task[None] | None = None
        self.notification_task: asyncio.Task[None] | None = None
        self.notification_queue: asyncio.Queue[QueuedLowStockEmail] = asyncio.Queue()
        self.monitor_generation = 0
        self.stop_event: asyncio.Event | None = None
        self.status = MonitorStatus(
            interval_seconds=SystemSettings().monitor_interval_seconds,
            email_notifications_enabled=self.notifier.enabled,
        )

    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def current_status(self) -> MonitorStatus:
        return self.status.model_copy(update={"running": self.running()})

    def update_interval(self, interval_seconds: float) -> None:
        self.status = self.status.model_copy(
            update={"interval_seconds": interval_seconds}
        )

    async def start(self) -> MonitorStatus:
        settings = self.store.load()
        if self.running():
            raise HTTPException(status_code=409, detail="常時監視はすでに動作中です")
        if self.operation_lock.locked():
            raise HTTPException(status_code=409, detail="別の撮影・測定を実行中です")
        async with self.operation_lock:
            runtime = await self.workflow.ensure_calibrations(settings)
        self.stop_event = asyncio.Event()
        self._ensure_notification_worker()
        self.monitor_generation += 1
        self.email_tracker.reset()
        self.status = MonitorStatus(
            running=True,
            interval_seconds=settings.monitor_interval_seconds,
            started_at=now_iso(),
            email_notifications_enabled=self.notifier.enabled,
            last_result=self.status.last_result,
        )
        self.task = asyncio.create_task(
            self.run_loop(self.stop_event, settings, runtime)
        )
        return self.current_status()

    def stop(self) -> MonitorStatus:
        if not self.running() or self.stop_event is None:
            raise HTTPException(status_code=409, detail="常時監視は停止しています")
        self.stop_event.set()
        self.status = self.status.model_copy(update={"stopping": True})
        return self.current_status()

    async def shutdown(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        if self.running() and self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        if self.notification_task is not None:
            self.notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.notification_task
            self.notification_task = None

    async def run_loop(
        self,
        stop_event: asyncio.Event,
        settings: SystemSettings,
        runtime: RuntimeState,
    ) -> None:
        loop = asyncio.get_running_loop()
        persistence_limit = asyncio.Semaphore(settings.measurement_concurrency)
        try:
            while not stop_event.is_set():
                # SettingsStoreはメモリキャッシュを返す。監視中に許可された
                # 低在庫しきい値だけを次周期から反映し、DB読込みは増やさない。
                settings = self.store.load()
                cycle_started = loop.time()
                started_at = datetime.now(UTC)
                self.status = self.status.model_copy(
                    update={
                        "last_started_at": started_at.isoformat(),
                        "interval_seconds": settings.monitor_interval_seconds,
                    }
                )
                try:
                    async with self.operation_lock:
                        outcomes = await self.workflow.measure_camera_jobs(
                            settings,
                            runtime,
                            generate_artifacts=False,
                            persistent=False,
                        )
                    successes = [
                        outcome for outcome in outcomes
                        if outcome.result is not None
                    ]
                    failures = [
                        outcome for outcome in outcomes
                        if outcome.error is not None
                    ]
                    annotated = [
                        (outcome, annotate_low_stock(outcome.result, settings))
                        for outcome in successes
                        if outcome.result is not None
                    ]
                    if self.history is not None:
                        stored = await self._store_outcomes(
                            annotated,
                            failures,
                            settings,
                            persistence_limit,
                        )
                    else:
                        stored = annotated
                    for outcome, measured_result in stored:
                        self._queue_low_stock_alerts(
                            measured_result,
                            settings,
                            finished_at=outcome.finished_at,
                        )
                    result = combine_measurements([
                        measured_result for _outcome, measured_result in annotated
                    ]) if annotated else None
                    error = format_camera_errors(failures) if failures else None
                    issues = [
                        issue_from_measurement_error(
                            outcome.error,
                            camera_id=outcome.camera_id,
                            occurred_at=outcome.finished_at.isoformat(),
                        )
                        for outcome in failures
                        if outcome.error is not None
                    ]
                    last_outcome = (
                        "partial_failure" if successes and failures
                        else "success" if successes
                        else "failed"
                    )
                    self.status = self.status.model_copy(
                        update={
                            "completed_measurements": (
                                self.status.completed_measurements + (1 if successes else 0)
                            ),
                            "consecutive_errors": (
                                0 if successes else self.status.consecutive_errors + 1
                            ),
                            "last_finished_at": now_iso(),
                            "last_error": error,
                            "last_outcome": last_outcome,
                            "last_issues": issues,
                            "last_result": result or self.status.last_result,
                        }
                    )
                except Exception as exc:
                    finished_at = datetime.now(UTC)
                    if self.history is not None:
                        await asyncio.to_thread(
                            self.history.record_failure,
                            started_at=started_at,
                            finished_at=finished_at,
                            error_message=error_detail(exc),
                        )
                    self.status = self.status.model_copy(
                        update={
                            "consecutive_errors": self.status.consecutive_errors + 1,
                            "last_finished_at": finished_at.isoformat(),
                            "last_error": error_detail(exc),
                            "last_outcome": "failed",
                            "last_issues": [issue_from_monitor_error(
                                exc,
                                occurred_at=finished_at.isoformat(),
                            )],
                        }
                    )
                if stop_event.is_set():
                    break
                elapsed = loop.time() - cycle_started
                wait_seconds = max(
                    0.0, settings.monitor_interval_seconds - elapsed
                )
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=wait_seconds,
                    )
                except TimeoutError:
                    pass
        finally:
            self.status = self.status.model_copy(
                update={"running": False, "stopping": False}
            )

    async def _store_outcomes(
        self,
        annotated: list[tuple[CameraMeasurementOutcome, MeasurementResponse]],
        failures: list[CameraMeasurementOutcome],
        settings: SystemSettings,
        limit: asyncio.Semaphore,
    ) -> list[tuple[CameraMeasurementOutcome, MeasurementResponse]]:
        assert self.history is not None

        async def save_success(
            outcome: CameraMeasurementOutcome,
            result: MeasurementResponse,
        ) -> tuple[CameraMeasurementOutcome, MeasurementResponse] | None:
            async with limit:
                saved = await asyncio.to_thread(
                    self.history.record_success,
                    result,
                    settings,
                    started_at=outcome.started_at,
                    finished_at=outcome.finished_at,
                )
            return (outcome, result) if saved else None

        async def save_failure(outcome: CameraMeasurementOutcome) -> None:
            assert outcome.error is not None
            async with limit:
                await asyncio.to_thread(
                    self.history.record_failure,
                    camera_id=outcome.camera_id,
                    started_at=outcome.started_at,
                    finished_at=outcome.finished_at,
                    error_message=error_detail(outcome.error),
                )

        saved, _ = await asyncio.gather(
            asyncio.gather(*(save_success(*item) for item in annotated)),
            asyncio.gather(*(save_failure(item) for item in failures)),
        )
        return [item for item in saved if item is not None]

    def _queue_low_stock_alerts(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
        *,
        finished_at: datetime,
    ) -> None:
        alerts = self.email_tracker.evaluate(result, settings)
        if not alerts or not self.notifier.enabled:
            return
        camera_runs = {run.camera_id: run for run in result.camera_runs}
        for alert in alerts:
            camera_run = camera_runs.get(alert.camera_id)
            if camera_run is None:
                self.status = self.status.model_copy(update={
                    "last_email_error": "メール対象カメラの測定履歴がありません",
                })
                continue
            self.email_tracker.mark_queued(alert.pallet_id)
            self.notification_queue.put_nowait(QueuedLowStockEmail(
                alert=alert,
                calibration_id=camera_run.calibration_id,
                finished_at=finished_at,
                monitor_generation=self.monitor_generation,
            ))

    async def _send_low_stock_alerts(
        self,
        result: MeasurementResponse,
        settings: SystemSettings,
        *,
        finished_at: datetime,
    ) -> None:
        """通知キューを同期的に検証するテスト・保守用入口。"""
        self._ensure_notification_worker()
        self._queue_low_stock_alerts(result, settings, finished_at=finished_at)
        await self.notification_queue.join()

    def _ensure_notification_worker(self) -> None:
        if self.notification_task is None or self.notification_task.done():
            self.notification_task = asyncio.create_task(
                self._notification_worker(),
                name="low-stock-email-worker",
            )

    async def _notification_worker(self) -> None:
        while True:
            queued = await self.notification_queue.get()
            try:
                sent_at = await asyncio.to_thread(self._send_and_record, queued)
                if queued.monitor_generation == self.monitor_generation:
                    self.email_tracker.mark_sent(queued.alert.pallet_id)
                    self.status = self.status.model_copy(update={
                        "last_email_sent_at": sent_at.isoformat(),
                        "last_email_error": None,
                        "last_email_issue": None,
                    })
            except Exception as exc:
                if queued.monitor_generation == self.monitor_generation:
                    failed_at = datetime.now(UTC)
                    self.email_tracker.mark_failed(queued.alert.pallet_id)
                    self.status = self.status.model_copy(update={
                        "last_email_error": error_detail(exc),
                        "last_email_issue": issue_from_email_error(
                            exc,
                            occurred_at=failed_at.isoformat(),
                        ),
                    })
            finally:
                self.notification_queue.task_done()

    def _send_and_record(self, queued: QueuedLowStockEmail) -> datetime:
        self.notifier.send(queued.alert)
        sent_at = datetime.now(UTC)
        if self.history is not None:
            saved = self.history.mark_email_sent(
                calibration_id=queued.calibration_id,
                pallet_number=queued.alert.pallet_number,
                finished_at=queued.finished_at,
                sent_at=sent_at,
            )
            if not saved:
                raise RuntimeError("メール送信時刻をDBへ保存できません")
        return sent_at


@dataclass(frozen=True)
class QueuedLowStockEmail:
    alert: LowStockAlert
    calibration_id: str
    finished_at: datetime
    monitor_generation: int


def annotate_low_stock(
    result: MeasurementResponse,
    settings: SystemSettings,
) -> MeasurementResponse:
    pallets = {pallet.pallet_id: pallet for pallet in settings.pallets}
    return result.model_copy(update={
        "pallets": [
            measured.model_copy(update={
                "is_low_stock": (
                    evaluate_low_stock(
                        measured.volume_liters,
                        pallets[measured.pallet_id].low_stock_threshold_liters,
                    ).is_low_stock
                ),
                "low_stock_threshold_liters": (
                    pallets[measured.pallet_id].low_stock_threshold_liters
                ),
            })
            if measured.pallet_id in pallets else measured
            for measured in result.pallets
        ]
    })
