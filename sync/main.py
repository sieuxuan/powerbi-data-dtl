"""CLI cho hệ thống đồng bộ Excel/CSV vào SQL targets."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from core.config import ConfigError, connection_by_id, load_config
from core.db import create_sql_target_client
from core.logging_setup import setup_logging
from core.scheduler import run_foreground
from core.service import handle_service_command
from core.sync_engine import SyncEngine


LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch commands."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "service" and args.action in {"start", "stop", "remove"}:
            logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
            handle_service_command(args.action, args.config)
            return 0

        config = load_config(args.config)
        setup_logging(config.logging, config.base_dir)

        if args.command == "check-config":
            LOGGER.info(
                "Config OK: %s file job(s), %s enabled. API=%s:%s enabled=%s.",
                len(config.files),
                sum(1 for item in config.files if item.enabled),
                config.api.host,
                config.api.port,
                config.api.enabled,
            )
            return 0

        if args.command == "service":
            handle_service_command(args.action, args.config)
            return 0

        engine = SyncEngine(config)
        if args.command == "test-db":
            connection_config = connection_by_id(config, args.connection_id)
            create_sql_target_client(connection_config).test_connection()
            LOGGER.info("Database connection OK: %s (%s).", connection_config.name, connection_config.engine)
            return 0
        if args.command == "run-all":
            results = engine.run_all(force=args.force)
            _log_summary(results)
            return 0 if all(result.status in {"success", "skipped"} for result in results) else 1
        if args.command == "run":
            result = engine.run_by_name(args.name, force=args.force)
            _log_summary([result])
            return 0 if result.status in {"success", "skipped"} else 1
        if args.command == "status":
            _log_jobs(engine.list_jobs())
            _log_recent_logs(engine.recent_logs(args.limit))
            return 0
        if args.command == "start":
            run_foreground(config)
            return 0

        parser.print_help()
        return 2
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR, format="[%(levelname)s] %(message)s")
        LOGGER.error("Config error: %s", exc)
        return 2
    except Exception as exc:
        LOGGER.exception("Command failed: %s", exc)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Excel/CSV to SQL sync")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to config.yaml",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-config", help="Validate config.yaml")
    test_db_parser = subparsers.add_parser("test-db", help="Test a configured SQL connection")
    test_db_parser.add_argument("--connection-id", default="default", help="database_connections id to test")
    subparsers.add_parser("start", help="Start scheduler/API foreground runtime")

    run_all_parser = subparsers.add_parser("run-all", help="Run all enabled file sync jobs once")
    run_all_parser.add_argument("--force", action="store_true", help="Ignore skip_unchanged hash checks")

    run_parser = subparsers.add_parser("run", help="Run one configured file sync job")
    run_parser.add_argument("-n", "--name", required=True, help="Configured file name")
    run_parser.add_argument("--force", action="store_true", help="Ignore skip_unchanged hash checks")

    status_parser = subparsers.add_parser("status", help="Show configured jobs and recent sync logs")
    status_parser.add_argument("--limit", type=int, default=20, help="Number of recent logs to show")

    service_parser = subparsers.add_parser("service", help="Manage the Windows service")
    service_parser.add_argument("action", choices=["install", "start", "stop", "remove"])

    return parser


def _log_summary(results: list[object]) -> None:
    """Log a compact command summary."""
    for result in results:
        LOGGER.info(
            "Result: name=%s table=%s status=%s rows=%s hash=%s message=%s",
            result.name,
            result.table,
            result.status,
            result.rows_imported,
            result.file_hash,
            result.message,
        )


def _log_jobs(jobs: list[dict[str, object]]) -> None:
    """Log configured job statuses."""
    LOGGER.info("Configured jobs: %s", len(jobs))
    for job in jobs:
        latest = job.get("last_run") or {}
        LOGGER.info(
            "Job: name=%s enabled=%s connection=%s table=%s mode=%s cron=%s running=%s last_status=%s last_finished=%s",
            job.get("name"),
            job.get("enabled"),
            job.get("connection_id"),
            job.get("table"),
            job.get("sync_mode"),
            job.get("cron"),
            job.get("running", False),
            latest.get("status") if isinstance(latest, dict) else None,
            latest.get("finished_at") if isinstance(latest, dict) else None,
        )


def _log_recent_logs(logs: list[dict[str, object]]) -> None:
    """Log recent sync logs."""
    LOGGER.info("Recent sync logs: %s", len(logs))
    for row in logs:
        LOGGER.info(
            "Log: id=%s job=%s connection=%s table=%s status=%s rows=%s started=%s error=%s",
            row.get("id"),
            row.get("job_name"),
            row.get("connection_id"),
            row.get("table_name"),
            row.get("status"),
            row.get("rows_imported"),
            row.get("started_at"),
            row.get("error_message"),
        )


if __name__ == "__main__":
    sys.exit(main())
