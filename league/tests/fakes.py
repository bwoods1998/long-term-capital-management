"""A deterministic clock for trusted operator tests."""
class Clock:
    def __init__(self, start: float = 1789000000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


def iso(clock) -> str:
    from league.ledger import now_iso

    return now_iso(clock)


