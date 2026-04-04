import json
from pathlib import Path

STATE_FILE = Path("data/state.json")


class StateStore:

    def save(self, account_state, positions: dict, orders: dict):
        STATE_FILE.parent.mkdir(exist_ok=True)

        data = {
            "account": {
                "balances": account_state.balances,
                "available": account_state.available,
                "last_update": account_state.last_update
            },
            "positions": {
                k: vars(v) for k, v in positions.items()
            },
            "orders": {
                k: vars(v) for k, v in orders.items()
            }
        }

        STATE_FILE.write_text(json.dumps(data, indent=2))

    def load(self):
        if not STATE_FILE.exists():
            return None

        return json.loads(STATE_FILE.read_text())
