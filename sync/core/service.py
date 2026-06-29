"""Windows Service wrapper cho sync runtime."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import load_config
from .logging_setup import setup_logging
from .scheduler import SyncRuntime


LOGGER = logging.getLogger(__name__)
SERVICE_NAME = "PowerBIDataDTLSync"
DISPLAY_NAME = "PowerBI Data DTL Sync"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def handle_service_command(action: str, config_path: str | Path) -> None:
    """Install, start, stop, or remove the Windows service."""
    try:
        import win32service
        import win32serviceutil
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Windows Service commands.") from exc

    config_value = str(Path(config_path).resolve())
    if action == "install":
        win32serviceutil.InstallService(
            "core.service.SyncWindowsService",
            SERVICE_NAME,
            DISPLAY_NAME,
            startType=win32service.SERVICE_AUTO_START,
        )
        win32serviceutil.SetServiceCustomOption(SERVICE_NAME, "config_path", config_value)
        LOGGER.info("Installed service %s with config %s.", SERVICE_NAME, config_value)
    elif action == "start":
        win32serviceutil.StartService(SERVICE_NAME)
        LOGGER.info("Started service %s.", SERVICE_NAME)
    elif action == "stop":
        win32serviceutil.StopService(SERVICE_NAME)
        LOGGER.info("Stopped service %s.", SERVICE_NAME)
    elif action == "remove":
        win32serviceutil.RemoveService(SERVICE_NAME)
        LOGGER.info("Removed service %s.", SERVICE_NAME)
    else:
        raise ValueError(f"Unsupported service action: {action}")


def _service_framework_base() -> type:
    """Import pywin32 ServiceFramework lazily so non-service commands can compile."""
    try:
        import win32serviceutil

        return win32serviceutil.ServiceFramework
    except ImportError:
        class MissingServiceFramework:
            def __init__(self, _args: list[str]) -> None:
                raise RuntimeError("pywin32 is required for Windows Service commands.")

        return MissingServiceFramework


class SyncWindowsService(_service_framework_base()):
    """pywin32 service class."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = DISPLAY_NAME
    _svc_description_ = "Scheduled Excel/CSV to PostgreSQL sync service."

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        import win32event

        self.stop_handle = win32event.CreateEvent(None, 0, 0, None)
        self.runtime: SyncRuntime | None = None

    def SvcStop(self) -> None:
        """Request service shutdown."""
        import servicemanager
        import win32event
        import win32service

        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopping")
        if self.runtime:
            self.runtime.stop_event.set()
            self.runtime.stop()
        win32event.SetEvent(self.stop_handle)

    def SvcDoRun(self) -> None:
        """Run the sync runtime as a Windows Service."""
        import servicemanager
        import win32event
        import win32serviceutil

        config_path = win32serviceutil.GetServiceCustomOption(SERVICE_NAME, "config_path", str(DEFAULT_CONFIG))
        config = load_config(config_path)
        setup_logging(config.logging, config.base_dir)
        servicemanager.LogInfoMsg(f"{SERVICE_NAME} starting with config {config_path}")
        self.runtime = SyncRuntime(config)
        self.runtime.start()
        win32event.WaitForSingleObject(self.stop_handle, win32event.INFINITE)


if __name__ == "__main__":
    import win32serviceutil

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    win32serviceutil.HandleCommandLine(SyncWindowsService)
