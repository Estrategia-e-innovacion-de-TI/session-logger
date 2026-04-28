from __future__ import annotations

from typing import Any, Protocol


class Sanitizer(Protocol):
    def sanitize(self, value: Any, key: str | None = None) -> Any:
        ...
