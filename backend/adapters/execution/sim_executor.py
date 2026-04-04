class SimExecutor:
    """
    Chỉ forward signal, không gửi sàn
    """

    def __init__(self):
        self.orders = []

    def execute(self, signal: dict):
        # paper mode: coi như fill ngay
        self.orders.append(signal)
        return {
            "status": "FILLED",
            "signal": signal
        }
