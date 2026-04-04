class Position:
    def __init__(self, data: dict):
        self.data = data
        self.side = data["side"]
        self.sl = data["sl"]
        self.tp = data["tp"]
        self.risk = data["risk"]

    def as_dict(self):
        return self.data
