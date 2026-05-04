from __future__ import annotations

from collections import Counter


class InMemoryMetrics:
    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()

    def increment(self, name: str, value: int = 1) -> None:
        self._counter[name] += value

    def snapshot(self) -> dict[str, int]:
        return dict(self._counter)

