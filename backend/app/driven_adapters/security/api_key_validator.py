from __future__ import annotations

import secrets


class ApiKeyValidator:
    def __init__(self, valid_api_keys: tuple[str, ...]) -> None:
        self.valid_api_keys = valid_api_keys

    def is_valid(self, token: str) -> bool:
        return any(secrets.compare_digest(token, expected) for expected in self.valid_api_keys)

