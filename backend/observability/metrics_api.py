from fastapi import APIRouter
from .metrics_registry import metrics_registry

router = APIRouter()


@router.get("/metrics")
def get_metrics():
    return metrics_registry.snapshot()
