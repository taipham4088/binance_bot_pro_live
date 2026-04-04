from fastapi import APIRouter
from backend.backtest.replay_engine import backtest_engine
from pydantic import BaseModel

import os

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