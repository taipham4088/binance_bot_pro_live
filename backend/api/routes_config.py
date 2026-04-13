from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

router = APIRouter()

class EngineType(str, Enum):
    range_trend = "range_trend"
    range_trend_1m = "range_trend_1m"
    range_trend_15m = "range_trend_15m"
    range_trend_1h = "range_trend_1h"


class EngineProfile(str, Enum):
    range_trend = "range_trend"
    range_trend_1m = "range_trend_1m"
    range_trend_15m = "range_trend_15m"
    range_trend_1h = "range_trend_1h"


class PositionMode(str, Enum):
    long_only = "long_only"
    short_only = "short_only"
    dual = "dual"
# ============================================================
# Request / Response Models
# ============================================================

class ConfigSwitchRequest(BaseModel):
    session_id: str
    
    engine: Optional[EngineType] = None
    engine_profile: Optional[EngineProfile] = None
    position_mode: Optional[PositionMode] = None

    symbol: Optional[str] = None
    mode: Optional[str] = None   # paper | live | backtest


class ConfigJobResponse(BaseModel):
    job_id: str


# ============================================================
# Create Config Switch Job
# ============================================================

@router.post("/config/switch", response_model=ConfigJobResponse)
async def switch_config(req: Request, payload: ConfigSwitchRequest):

    engine = req.app.state.config_job_engine

    # Build new config (ONLY config, no execution)
    new_config = {}

    if payload.engine:
        new_config["engine"] = payload.engine.value

    if payload.engine_profile:
        new_config["engine_profile"] = payload.engine_profile.value

    if payload.position_mode:
        new_config["position_mode"] = payload.position_mode.value

    if payload.symbol:
        new_config["symbol"] = payload.symbol

    if payload.mode:
        new_config["mode"] = payload.mode

    if not new_config:
        raise HTTPException(status_code=400, detail="Empty config update")

    try:
        job_id = await engine.create_job(
            session_id=payload.session_id,
            new_config=new_config
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"job_id": job_id}


# ============================================================
# Query Job Status
# ============================================================

@router.get("/config/job/{job_id}")
def get_job(job_id: str, req: Request):

    engine = req.app.state.config_job_engine
    job = engine.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "current_state": job.current_state,
        "error": job.error,
        "audit_log": job.audit_log,
    }
