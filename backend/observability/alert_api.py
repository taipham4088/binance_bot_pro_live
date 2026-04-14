from fastapi import APIRouter

from backend.alerts.alert_store import alert_store

from .alert_engine import alert_engine_instance

router = APIRouter()


@router.get("/api/alerts")
def get_alerts():
    try:
        return alert_store.get_all()
    except Exception:
        return []


@router.get("/alerts")
def get_alert_engine_alerts():
    return alert_engine_instance.get_alerts()
