class BaseStrategy:

    name = "base"

    def generate_intent(self, market_state):
        """
        return trading intent
        """
        raise NotImplementedError
