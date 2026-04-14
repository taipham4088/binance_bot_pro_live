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
_IMPORT_STAGE_DIR = _IMPORT_DIR / ".staging_download"

router = APIRouter(tags=["data"])


def _clear_stage_csv() -> None:
    _IMPORT_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    for p in _IMPORT_STAGE_DIR.glob("*.csv"):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass


def _cleanup_old_import_csv(keep_file: Path) -> None:
    _IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    for p in _IMPORT_DIR.glob("*.csv"):
        if not p.is_file():
            continue
        if p.resolve() == keep_file.resolve():
            continue
        try:
            print(f"[DATA] Removing old dataset: {p.name}")
            p.unlink()
        except OSError:
            pass


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
        _clear_stage_csv()
        if market == "spot":
            path = download_binance_spot_data(
                symbol=req.symbol.strip(),
                interval=req.interval.strip(),
                start_date=req.start_date.strip(),
                end_date=req.end_date.strip(),
                out_dir=_IMPORT_STAGE_DIR,
            )
        elif market == "futures":
            path = download_binance_data(
                symbol=req.symbol.strip(),
                interval=req.interval.strip(),
                start_date=req.start_date.strip(),
                end_date=req.end_date.strip(),
                out_dir=_IMPORT_STAGE_DIR,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="market must be 'spot' or 'futures'.",
            )
        _IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        final_path = _IMPORT_DIR / path.name
        # Atomic promote: dataset old remains untouched until this succeeds.
        path.replace(final_path)
        _cleanup_old_import_csv(keep_file=final_path)
        path = final_path
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    rel = path.relative_to(_REPO_ROOT)
    print(f"[DATA] Saved new dataset: {path.name}")
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
