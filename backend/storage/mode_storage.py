import os


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

    # =========================
    # TRADE PATH
    # =========================

    def get_trade_path(self, mode):

        folder = self.paths.get(mode, self.paths["shadow"])

        return os.path.join(folder, "trades.db")

    # =========================
    # EXECUTION PATH
    # =========================

    def get_execution_path(self, mode):

        folder = self.paths.get(mode, self.paths["shadow"])

        return os.path.join(folder, "execution.db")

    # =========================
    # EVENTS PATH
    # =========================

    def get_event_path(self, mode):

        folder = self.paths.get(mode, self.paths["shadow"])

        return os.path.join(folder, "events.log")

    # =========================
    # BACKTEST EXPORT PATH
    # =========================

    def get_backtest_export(self):

        folder = self.paths["backtest"]

        return os.path.join(folder, "output")


mode_storage = ModeStorage()