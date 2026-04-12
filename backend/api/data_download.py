"""REST API for standalone Binance spot/futures kline download (read-only; saves under data/import/)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tools.binance_data_downloader import download_binance_data
from tools.binance_spot_downloader import download_binance_spot_data

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPORT_DIR = _REPO_ROOT / "data" / "import"

router = APIRouter(tags=["data"])


class DownloadRequest(BaseModel):
    exchange: str = Field(..., min_length=1)
    market: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    interval: str
    start_date: str = Field(..., min_length=1)
    end_date: str = Field(..., min_length=1)


@router.post("/api/data/download")
def download_data(req: DownloadRequest):
    ex = req.exchange.strip().lower()
    if ex != "binance":
        raise HTTPException(
            status_code=400,
            detail="Only exchange 'binance' is supported currently.",
        )

    market = req.market.strip().lower()
    try:
        if market == "spot":
            path = download_binance_spot_data(
                symbol=req.symbol.strip(),
                interval=req.interval.strip(),
                start_date=req.start_date.strip(),
                end_date=req.end_date.strip(),
                out_dir=_IMPORT_DIR,
            )
        elif market == "futures":
            path = download_binance_data(
                symbol=req.symbol.strip(),
                interval=req.interval.strip(),
                start_date=req.start_date.strip(),
                end_date=req.end_date.strip(),
                out_dir=_IMPORT_DIR,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="market must be 'spot' or 'futures'.",
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    rel = path.relative_to(_REPO_ROOT)
    return {
        "success": True,
        "file": str(path),
        "path": rel.as_posix(),
        "filename": path.name,
    }


@router.get("/api/data/import-files")
def list_import_csv_files():
    """CSV files in data/import/ (for dashboard refresh after download)."""
    _IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(
        f
        for f in os.listdir(_IMPORT_DIR)
        if f.endswith(".csv") and (_IMPORT_DIR / f).is_file()
    )
    return {
        "files": [{"name": n, "path": f"data/import/{n}"} for n in names],
    }
