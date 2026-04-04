from trading_core.engines.long_engine_raw import process_long as _process_long
from trading_core.engines.long_engine_raw import init_long_state as _init_state


class LongEngine:
    def __init__(self):
        self.state = _init_state()

    def on_bar(self, i, row, df, context, equity):
        return _process_long(i, row, df, self.state, equity, context)
