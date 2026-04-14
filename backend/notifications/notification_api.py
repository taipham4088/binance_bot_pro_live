from fastapi import APIRouter

from backend.notifications.notification_manager import notification_manager

router = APIRouter()


@router.get("/api/notifications")
def get_notifications():
    try:
        return notification_manager.get_recent()
    except Exception:
        return []
