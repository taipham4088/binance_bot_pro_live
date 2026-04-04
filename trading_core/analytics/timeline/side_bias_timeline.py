from trading_core.analytics.states.side_bias import SideBiasEngine


class SideBiasTimeline:

    def __init__(self, window=50):
        self.window = window
        self.engine = SideBiasEngine()

    def build(self, trades):
        timeline = []

        for i in range(self.window, len(trades)+1):
            sub = trades[:i]
            state = self.engine.infer(sub, window=self.window)

            timeline.append({
                "exit_time": sub[-1]["exit_time"],
                "state": state
            })

        return timeline
