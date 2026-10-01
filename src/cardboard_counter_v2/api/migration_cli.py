"""本番起動前に明示実行するDB・旧データ移行コマンド。"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from alembic import command
from alembic.config import Config

from cardboard_counter_v2.api.box_catalog_repository import BoxCatalogRepository
from cardboard_counter_v2.api.capture_migration import LegacyCaptureMigrator
from cardboard_counter_v2.api.capture_layout_migration import CaptureLayoutMigrator
from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.repository import InventoryRepository
from cardboard_counter_v2.api.settings import SettingsStore
from cardboard_counter_v2.common.storage import data_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Cardboard Counterデータ移行")
    subparsers = parser.add_subparsers(dest="target", required=True)
    db_parser = subparsers.add_parser("db", help="DBスキーマ移行")
    db_parser.add_argument("action", choices=("upgrade", "current"))
    data_parser = subparsers.add_parser("data", help="旧JSON・Capture移行")
    data_parser.add_argument("action", choices=("plan", "upgrade"))
    layout_parser = subparsers.add_parser(
        "capture-layout", help="Capture保存ディレクトリ移行"
    )
    layout_parser.add_argument("action", choices=("plan", "upgrade"))
    args = parser.parse_args()
    if args.target == "db":
        return run_db(args.action)
    if args.target == "capture-layout":
        return run_capture_layout(args.action)
    return run_data(args.action)


def run_db(action: str) -> int:
    config = alembic_config()
    if action == "current":
        command.current(config, verbose=True)
    else:
        command.upgrade(config, "head")
        print("DBマイグレーションが完了しました")
    return 0


def run_data(action: str) -> int:
    database = Database()
    database.initialize()
    root = data_root()
    legacy_settings = root / "config" / "settings.json"
    migrator = LegacyCaptureMigrator(database, root)
    if action == "plan":
        report = migrator.validate()
        print(f"旧settings.json: {'1件' if legacy_settings.is_file() else 'なし'}")
        print(f"旧Capture候補: {report.candidates}件")
        _print_errors(report.errors)
        return 0 if report.successful else 1

    store = SettingsStore(
        InventoryRepository(database),
        BoxCatalogRepository(database),
        legacy_settings,
    )
    if legacy_settings.is_file():
        backup = root / "backups" / "settings_v1" / "settings.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            shutil.copy2(legacy_settings, backup)
        store.migrate_legacy_json()
        print("旧settings.jsonをDBへ移行しました")
    else:
        # Capture登録に必要なカメラマスターが存在することを保証する。
        store.load()

    report = migrator.apply()
    print(f"旧Capture候補: {report.candidates}件")
    print(f"移行成功: {report.migrated}件")
    _print_errors(report.errors)
    if report.successful:
        _archive_obsolete_json(root)
        print("旧データ移行が完了しました")
        return 0
    print("失敗したCaptureの元ファイルは削除していません")
    return 1


def run_capture_layout(action: str) -> int:
    database = Database()
    database.initialize()
    migrator = CaptureLayoutMigrator(database, data_root())
    report = migrator.validate() if action == "plan" else migrator.apply()
    print(f"配置移行候補: {report.candidates}件")
    if action == "upgrade":
        print(f"移行成功: {report.migrated}件")
    _print_errors(report.errors)
    if report.successful:
        print(
            "Capture配置の検証が完了しました"
            if action == "plan"
            else "Capture配置の移行が完了しました"
        )
        return 0
    print("エラーがあるCaptureは変更していません")
    return 1


def alembic_config() -> Config:
    source_root = Path(__file__).resolve().parents[3]
    config_path = source_root / "alembic.ini"
    if not config_path.is_file():
        config_path = Path("/app/alembic.ini")
    config = Config(str(config_path))
    script_location = Path(__file__).resolve().parent / "alembic"
    config.set_main_option("script_location", str(script_location))
    return config


def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}")


def _archive_obsolete_json(root: Path) -> None:
    backup_root = root / "backups" / "obsolete_json"
    for relative in (
        Path("state/runtime.json"),
        Path("state/last_result.json"),
        Path("state/last_debug_result.json"),
        Path("camera/config.json"),
    ):
        source = root / relative
        if not source.is_file():
            continue
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        source.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
