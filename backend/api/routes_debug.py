from fastapi import APIRouter, Request

router = APIRouter(tags=["debug"])


def _export_candle_for_session(request: Request, session: str) -> dict:
    manager = request.app.state.manager
    sid = (session or "live").strip().lower()
    sess = manager.get(sid)
    if not sess:
        return {"ok": False, "error": "session not found"}

    market = getattr(sess, "market", None)
    if market is None or not hasattr(market, "feature_engine"):
        return {"ok": False, "error": "market or feature_engine not available"}

    fe = market.feature_engine
    n = fe.export_now()
    if n is None:
        return {"ok": False, "error": "export failed or no candle data"}

    file_key = "live" if sid == "live" else "shadow" if sid == "shadow" else sid
    return {
        "ok": True,
        "session": sid,
        "rows": n,
        "path": f"data/debug/candle_{file_key}.csv",
    }


@router.post("/export-candle")
def post_export_candle(request: Request, session: str = "live"):
    return _export_candle_for_session(request, session)


@router.get("/export-candle")
def get_export_candle(request: Request, session: str = "live"):
    return _export_candle_for_session(request, session)
