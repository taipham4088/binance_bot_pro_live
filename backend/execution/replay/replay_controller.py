class ReplayController:
    """
    High-level control for UI / API
    """

    def __init__(self, engine):
        self._engine = engine
        self._paused = True

    def play(self):
        self._paused = False

    def pause(self):
        self._paused = True

    def step(self):
        return self._engine.step()

    def seek(self, index: int):
        self._engine.seek(index)

    def is_paused(self) -> bool:
        return self._paused
