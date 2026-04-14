from __future__ import annotations

import logging
from typing import Union

from backend.alerts.alert_bus import alert_bus
from backend.alerts.alert_store import alert_store
from backend.alerts.alert_types import Alert, AlertLevel, AlertSource

_logger = logging.getLogger(__name__)


def _level_str(level: Union[AlertLevel, str]) -> str:
    return level.value if isinstance(level, AlertLevel) else str(level)


def _source_str(source: Union[AlertSource, str]) -> str:
    return source.value if isinstance(source, AlertSource) else str(source)


class AlertManager:
    def create_alert(self, alert: Alert) -> None:
        try:
            lvl = _level_str(alert.level)
            src = _source_str(alert.source)
            line = f"[ALERT][{lvl}][{src}] {alert.message}"
            _logger.log(
                logging.CRITICAL if lvl == "CRITICAL" else logging.WARNING if lvl == "WARNING" else logging.INFO,
                line,
            )
            alert_store.add(alert)
            alert_bus.publish(alert)
        except Exception:
            pass


alert_manager = AlertManager()
