from fastapi import APIRouter
from .alert_engine import alert_engine_instance

router = APIRouter()


@router.get("/alerts")
def get_alerts():
    return alert_engine_instance.get_alerts()
