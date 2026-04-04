import sqlite3


class MetricsEngine:
    """
    Metrics Engine tính toán performance statistics:

    - total_trades
    - win_rate
    - avg_win
    - avg_loss
    - profit_factor
    """

    def __init__(self, db_path="data/trades.db"):

        self.db_path = db_path

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)

    def get_all_trades(self):

        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT pnl
            FROM trades
            """
        )

        rows = cursor.fetchall()

        return [r[0] for r in rows]

    def total_trades(self):

        return len(self.get_all_trades())

    def win_trades(self):

        trades = self.get_all_trades()

        return [p for p in trades if p > 0]

    def loss_trades(self):

        trades = self.get_all_trades()

        return [p for p in trades if p < 0]

    def win_rate(self):

        total = self.total_trades()

        if total == 0:
            return 0

        wins = len(self.win_trades())

        return wins / total

    def avg_win(self):

        wins = self.win_trades()

        if not wins:
            return 0

        return sum(wins) / len(wins)

    def avg_loss(self):

        losses = self.loss_trades()

        if not losses:
            return 0

        return sum(losses) / len(losses)

    def profit_factor(self):

        wins = sum(self.win_trades())
        losses = abs(sum(self.loss_trades()))

        if losses == 0:
            return None

        return wins / losses

    def summary(self):

        return {

            "total_trades": self.total_trades(),

            "win_rate": self.win_rate(),

            "avg_win": self.avg_win(),

            "avg_loss": self.avg_loss(),

            "profit_factor": self.profit_factor()

        }