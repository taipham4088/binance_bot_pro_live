class MarketModeEngine:

    def __init__(self, side_bias_stream, system_analyzer, emitter):
        self.side_bias_stream = side_bias_stream
        self.system_analyzer = system_analyzer
        self.emitter = emitter
        self.resolver = MarketModeResolver()

        self.side_bias = None
        self.equity_state = None

        self.side_bias_stream.subscribe(self.on_side_bias)
        self.system_analyzer.subscribe(self.on_system_state)

    def on_side_bias(self, bias):
        self.side_bias = bias
        self.recompute()

    def on_system_state(self, state):
        self.equity_state = state
        self.recompute()

    def recompute(self):
        if not self.side_bias or not self.equity_state:
            return

        market_state = self.resolver.resolve(
            side_bias=self.side_bias,
            equity_state=self.equity_state
        )

        self.emitter.emit("MARKET_MODE", market_state)
