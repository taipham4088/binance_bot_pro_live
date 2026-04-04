from trading_core.runners.backtest import prepare_data
from backend.core.strategy_host import StrategyHost


class BacktestService:

    def __init__(self):
        self.host = StrategyHost()

    def run(self, session, csv_path):

        df = prepare_data(csv_path)
        engine = self.host.create_engine(session.config)
        session.engine = engine

        for i in range(80, len(df)):
            engine.on_bar(i, df.iloc[i], df)

            # stream equity
            t, eq = engine.equity_tracker.curve[-1]
            session.state_bus.on_equity(t, eq)

        # stream trades
        for trade in engine.trades:
            session.state_bus.on_trade(trade)

        session.status = "FINISHED"
        return engine.trades, session.state_bus.snapshot()
