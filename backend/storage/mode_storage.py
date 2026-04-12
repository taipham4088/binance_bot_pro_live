import os
import shutil


class ModeStorage:

    def __init__(self):

        self.base = "data"

        self.paths = {
            "live": os.path.join(self.base, "live"),
            "shadow": os.path.join(self.base, "shadow"),
            "backtest": os.path.join(self.base, "backtest")
        }

        self._ensure_dirs()

    # =========================
    # ENSURE FOLDERS
    # =========================

    def _ensure_dirs(self):

        for path in self.paths.values():
            os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(self.base, "session"), exist_ok=True)
        os.makedirs(os.path.join(self.base, "archive"), exist_ok=True)

    # =========================
    # SESSION RUNTIME TRADE DB (isolated per dashboard session)
    # =========================

    def get_session_trade_path(self, session: str | None) -> str:
        """
        One SQLite file per session under data/session/, e.g. trades_live.db.
        """
        key = (session if session is not None else "shadow").strip().lower().replace("-", "_")
        session_dir = os.path.join(self.base, "session")
        os.makedirs(session_dir, exist_ok=True)
        new_path = os.path.join(session_dir, f"trades_{key}.db")
        self._maybe_migrate_legacy_trade_db(key, new_path)
        return new_path

    def get_archive_trade_path(self) -> str:
        """Append-only archive for cleared / archived closed trades."""
        archive_dir = os.path.join(self.base, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        return os.path.join(archive_dir, "trades_archive.db")

    def _maybe_migrate_legacy_trade_db(self, key: str, new_path: str) -> None:
        """One-time copy from data/<key>/trades.db when session file missing."""
        if os.path.isfile(new_path) and os.path.getsize(new_path) > 0:
            return
        legacy = os.path.join(self.base, key, "trades.db")
        if os.path.isfile(legacy):
            try:
                shutil.copy2(legacy, new_path)
            except OSError:
                pass

    # =========================
    # TRADE PATH (delegates to session layout)
    # =========================

    def get_trade_path(self, mode):

        key = mode if mode is not None else "shadow"
        return self.get_session_trade_path(str(key))

    # =========================
    # EXECUTION PATH
    # =========================

    def get_execution_path(self, mode):

        key = mode if mode is not None else "shadow"
        folder = self.paths.get(key)
        if folder is None:
            folder = os.path.join(self.base, str(key))
            os.makedirs(folder, exist_ok=True)

        return os.path.join(folder, "execution.db")

    # =========================
    # EVENTS PATH
    # =========================

    def get_event_path(self, mode):

        key = mode if mode is not None else "shadow"
        folder = self.paths.get(key)
        if folder is None:
            folder = os.path.join(self.base, str(key))
            os.makedirs(folder, exist_ok=True)

        return os.path.join(folder, "events.log")

    # =========================
    # BACKTEST EXPORT PATH
    # =========================

    def get_backtest_export(self):

        folder = self.paths["backtest"]

        return os.path.join(folder, "output")


mode_storage = ModeStorage()