from trading_core.analytics.streams.equity_stream import EquityStream
from trading_core.analytics.streams.drawdown_stream import DrawdownStream
from trading_core.analytics.streams.trade_stream import TradeStream

from trading_core.analytics.states.equity_state import EquityStateEngine
from trading_core.analytics.states.side_bias import SideBiasEngine

from trading_core.analytics.timeline.equity_timeline import EquityStateTimeline
from trading_core.analytics.timeline.side_bias_timeline import SideBiasTimeline


class SystemAnalyzer:

    def __init__(self):
        self.equity_engine = EquityStateEngine()
        self.side_engine = SideBiasEngine()

        self.equity_timeline = EquityStateTimeline()
        self.side_timeline = SideBiasTimeline()

    def analyze(self, backtest_result):

        equity_stream = EquityStream(backtest_result.equity_curve)
        dd_stream = DrawdownStream(equity_stream)
        trade_stream = TradeStream(backtest_result.trades)

        return {
            "equity_state": self.equity_engine.infer(equity_stream, dd_stream),
            "side_bias": self.side_engine.infer(backtest_result.trades),
            "max_dd": dd_stream.max_dd(),
            "expectancy": None,   # cắm metric layer sau
            "total_trades": len(backtest_result.trades)
        }

    def analyze_timeline(self, backtest_result):

        equity_tl = self.equity_timeline.build(backtest_result.equity_curve)
        side_tl = self.side_timeline.build(backtest_result.trades)

        return {
            "equity_timeline": equity_tl,
            "side_bias_timeline": side_tl
        }
