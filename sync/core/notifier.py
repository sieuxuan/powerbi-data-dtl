"""Thông báo desktop và email cho kết quả đồng bộ."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from .config import NotificationConfig


LOGGER = logging.getLogger(__name__)


class Notifier:
    """Best-effort notification sender."""

    def __init__(self, config: NotificationConfig) -> None:
        self.config = config

    def notify_result(self, result: object) -> None:
        """Send per-job notifications."""
        self._send_webhook(result)
        self._send_windows_toast(result)

    def send_summary(self, results: list[object]) -> None:
        """Send an email summary for a batch run."""
        email = self.config.email
        if not email.enabled or not results:
            return
        if not email.smtp_host or not email.sender or not email.recipients:
            LOGGER.warning("Email notification is enabled but SMTP sender/host/recipients are incomplete.")
            return

        counts: dict[str, int] = {}
        for result in results:
            counts[getattr(result, "status", "unknown")] = counts.get(getattr(result, "status", "unknown"), 0) + 1
        subject = "[Sync Report] " + ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
        lines = [
            f"{getattr(result, 'name', '')} | {getattr(result, 'table', '')} | "
            f"{getattr(result, 'status', '')} | rows={getattr(result, 'rows_imported', 0)} | "
            f"{getattr(result, 'message', '')}"
            for result in results
        ]

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = email.sender
        message["To"] = ", ".join(email.recipients)
        message.set_content("\n".join(lines))

        try:
            with smtplib.SMTP(email.smtp_host, email.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                if email.password:
                    smtp.login(email.sender, email.password)
                smtp.send_message(message)
        except Exception as exc:
            LOGGER.warning("Could not send email notification: %s", exc)

    def _send_windows_toast(self, result: object) -> None:
        """Send a desktop toast for important per-job results."""
        if not self.config.windows_toast:
            return
        if getattr(result, "status", "") == "skipped" and getattr(result, "details", {}).get("reason") == "unchanged":
            return
        title = f"Sync {getattr(result, 'status', 'unknown')}: {getattr(result, 'name', '')}"
        message = getattr(result, "message", "")
        try:
            from win11toast import toast

            toast(title, message)
        except Exception as exc:
            LOGGER.warning("Could not send Windows toast: %s", exc)

    def _send_webhook(self, result: object) -> None:
        """POST a JSON payload to the configured webhook URL."""
        webhook = self.config.webhook
        if not webhook.enabled:
            return
        status = str(getattr(result, "status", ""))
        allowed_statuses = {item.strip().lower() for item in webhook.statuses if item.strip()}
        if allowed_statuses and status.lower() not in allowed_statuses:
            return
        if not webhook.url:
            LOGGER.warning("Webhook notification is enabled but url is empty.")
            return
        payload = {"type": "sync_result", "result": _result_payload(result)}
        try:
            self.send_webhook_payload(payload)
        except Exception as exc:
            LOGGER.warning("Could not send webhook notification: %s", exc)

    def send_webhook_payload(self, payload: dict[str, Any]) -> None:
        """POST an arbitrary JSON payload to the configured webhook URL."""
        webhook = self.config.webhook
        if not webhook.enabled:
            raise ValueError("Webhook is disabled.")
        if not webhook.url:
            raise ValueError("Webhook URL is empty.")
        import httpx

        response = httpx.post(webhook.url, json=payload, timeout=webhook.timeout_seconds)
        response.raise_for_status()


def _result_payload(result: object) -> dict[str, Any]:
    """Return a JSON payload for a sync result-like object."""
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return {
        "name": getattr(result, "name", ""),
        "table": getattr(result, "table", ""),
        "status": getattr(result, "status", ""),
        "rows_imported": getattr(result, "rows_imported", 0),
        "message": getattr(result, "message", ""),
        "file_hash": getattr(result, "file_hash", None),
        "file_path": getattr(result, "file_path", None),
        "error_message": getattr(result, "error_message", None),
        "details": getattr(result, "details", {}),
    }
