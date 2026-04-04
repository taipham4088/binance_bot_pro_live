class RuntimeContext:
    def __init__(self, config):
        self.config = config

    @property
    def rr(self):
        if self.config.core_mode == "locked":
            return self.config.rr_locked
        return self.config.rr

    @property
    def risk_per_trade(self):
        return self.config.risk_per_trade
