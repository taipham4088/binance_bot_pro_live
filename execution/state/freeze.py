class ExecutionFreeze:

    def __init__(self):
        self.frozen = False
        self.reason = None

    def freeze(self, reason: str):
        if not self.frozen:
            self.frozen = True
            self.reason = reason
            print("🚨 EXECUTION FROZEN:", reason)

    def is_frozen(self):
        return self.frozen
