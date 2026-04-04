class BinanceRestSync:
    def __init__(self, client):
        self.client = client

    def snapshot(self):
        return {
            "balances": self.client.futures_account_balance(),
            "positions": self.client.futures_position_information(),
            "orders": self.client.futures_get_open_orders()
        }
