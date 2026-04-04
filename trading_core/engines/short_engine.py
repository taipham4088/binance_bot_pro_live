from trading_core.engines.short_engine_raw import process_short as _process_short
from trading_core.engines.short_engine_raw import init_short_state as _init_state


class ShortEngine:
    def __init__(self):
        self.state = _init_state()

    def on_bar(self, i, row, df, context, equity):
        return _process_short(i, row, df, self.state, equity, context)
