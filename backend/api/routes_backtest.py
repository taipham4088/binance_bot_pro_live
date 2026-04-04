from fastapi import APIRouter, Request
from backend.core.trading_session import TradingSession
from backend.services.backtest_service import BacktestService
from trading_core.config.engine_config import EngineConfig

router = APIRouter()
service = BacktestService()

@router.post("/run")
def run_backtest(req: dict, request: Request):

    manager = request.app.state.manager

    cfg = EngineConfig(**req["config"])

    session = TradingSession(
        mode="backtest",
        config=cfg,
        app=request.app
    )

    manager.register(session)

    trades, state = service.run(session, req["csv_path"])

    return {
        "session_id": session.id,
        "trades": len(trades),
        "system_state": state
    }
