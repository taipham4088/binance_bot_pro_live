from trading_core.analytics.streams.equity_stream import EquityStream
from trading_core.analytics.streams.drawdown_stream import DrawdownStream
from trading_core.analytics.states.equity_state import EquityStateEngine


class EquityStateTimeline:

    def __init__(self, lookback=50):
        self.engine = EquityStateEngine(lookback=lookback)

    def build(self, equity_curve):
        timeline = []

        for i in range(10, len(equity_curve)):
            sub = equity_curve[:i+1]

            equity_stream = EquityStream(sub)
            dd_stream = DrawdownStream(equity_stream)

            state = self.engine.infer(equity_stream, dd_stream)

            timeline.append({
                "time": sub[-1][0],
                "equity": sub[-1][1],
                "state": state,
                "dd": dd_stream.last()
            })

        return timeline
