import time

class CSVReplayFeed:
    """
    Replay dataframe như live feed
    """

    def __init__(self, df, speed=1.0):
        self.df = df
        self.speed = speed

    def stream(self, start_index=80):
        for i in range(start_index, len(self.df)):
            yield i, self.df.iloc[i]
            if self.speed > 0:
                time.sleep(self.speed)
