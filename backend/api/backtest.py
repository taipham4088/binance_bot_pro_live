import json
import os

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from backend.backtest.replay_engine import backtest_engine
from backend.services.backtest_service import BACKTEST_LATEST_CSV

router = APIRouter()

class BacktestStartRequest(BaseModel):
    file: str


@router.post("/backtest/start")
def start_backtest(req: BacktestStartRequest):

    backtest_engine.load_csv(req.file)

    backtest_engine.start()

    return {
        "status": "started",
        "file": req.file
    }

@router.get("/backtest/files")
def list_backtest_files():

    folder = "data/backtest/input"

    files = [
        f for f in os.listdir(folder)
        if f.endswith(".csv")
    ]

    return files


@router.get("/api/backtest/latest")
def get_backtest_latest_trades():
    """Return rows from the single canonical backtest export CSV (JSON array)."""
    if not os.path.isfile(BACKTEST_LATEST_CSV):
        return []
    try:
        df = pd.read_csv(BACKTEST_LATEST_CSV)
    except Exception:
        return []
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))