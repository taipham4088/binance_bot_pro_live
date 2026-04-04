from backend.ports.market_port import MarketPort
from backend.ports.execution_port import ExecutionPort
from backend.ports.account_port import AccountPort
from backend.adapters.data_feed.csv_replay_feed import CSVReplayFeed


class PaperMarketAdapter(MarketPort):

    def __init__(self, df, speed=0.0):
        self.feed = CSVReplayFeed(df, speed=speed)
        self.df = df
        self._latest_index = None
        self._latest_row = None

    # ===== pull style (core có thể gọi) =====

    def get_latest_candle(self, symbol=None, tf=None):
        return self._latest_index, self._latest_row

    # ===== push style (runner dùng) =====

    def subscribe_candle(self, callback, start_index=80):
        """
        callback(i, row, df)
        """
        for i, row in self.feed.stream(start_index=start_index):
            self._latest_index = i
            self._latest_row = row
            callback(i, row, self.df)
