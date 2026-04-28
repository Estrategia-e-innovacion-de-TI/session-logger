from __future__ import annotations

import json
import socket
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__
from .config import HttpConfig
from .sanitizer import sanitize_value
from .schema import EventRecord

SUCCESS_CODES = {200, 201, 202}
NON_RETRYABLE_CODES = {400, 401, 403}
RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(slots=True)
class HttpSendResult:
    success: bool
    retryable: bool
    status_code: int | None = None
    error: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


def _classify_status(status_code: int) -> HttpSendResult:
    if status_code in SUCCESS_CODES:
        return HttpSendResult(success=True, retryable=False, status_code=status_code)
    if status_code in NON_RETRYABLE_CODES:
        return HttpSendResult(
            success=False,
            retryable=False,
            status_code=status_code,
            error=f"http_{status_code}",
        )
    if status_code in RETRYABLE_CODES or 500 <= status_code <= 599:
        return HttpSendResult(
            success=False,
            retryable=True,
            status_code=status_code,
            error=f"http_{status_code}",
        )
    return HttpSendResult(
        success=False,
        retryable=False,
        status_code=status_code,
        error=f"unexpected_http_{status_code}",
    )


def _event_to_payload(event: EventRecord | dict[str, Any]) -> dict[str, Any]:
    payload = event.to_jsonable() if isinstance(event, EventRecord) else dict(event)
    sanitized = sanitize_value(payload)
    if not isinstance(sanitized, dict):
        raise TypeError("HTTP event payload must serialize to a JSON object.")
    return sanitized


class HttpEventSender:
    def __init__(self, config: HttpConfig) -> None:
        self.config = config

    def send_event(self, event: EventRecord | dict[str, Any]) -> HttpSendResult:
        if not self.config.endpoint:
            return HttpSendResult(success=False, retryable=False, error="endpoint_not_configured")
        if not self.config.api_key:
            return HttpSendResult(success=False, retryable=False, error="api_key_not_configured")

        try:
            payload = _event_to_payload(event)
        except (TypeError, ValueError) as exc:
            return HttpSendResult(success=False, retryable=False, error=str(exc))

        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        request = Request(
            self.config.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Logger-Version": __version__,
                "X-Event-Id": str(payload.get("event_id", "")),
            },
        )

        try:
            response = urlopen(request, timeout=self.config.timeout_seconds)
            try:
                status_code = int(getattr(response, "status", None) or response.getcode())
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            return _classify_status(status_code)
        except HTTPError as exc:
            return _classify_status(exc.code)
        except (TimeoutError, socket.timeout) as exc:
            return HttpSendResult(success=False, retryable=True, error=type(exc).__name__)
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return HttpSendResult(success=False, retryable=True, error=type(reason).__name__)
            return HttpSendResult(success=False, retryable=True, error="network_error")
        except OSError as exc:
            return HttpSendResult(success=False, retryable=True, error=type(exc).__name__)


def check_connectivity(endpoint: str, timeout_seconds: float, api_key: str | None = None) -> HttpSendResult:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(endpoint, method="HEAD", headers=headers)
    try:
        response = urlopen(request, timeout=timeout_seconds)
        try:
            status_code = int(getattr(response, "status", None) or response.getcode())
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if status_code < 500:
            return HttpSendResult(success=True, retryable=False, status_code=status_code)
        return _classify_status(status_code)
    except HTTPError as exc:
        if exc.code < 500:
            return HttpSendResult(success=True, retryable=False, status_code=exc.code)
        return _classify_status(exc.code)
    except (TimeoutError, socket.timeout) as exc:
        return HttpSendResult(success=False, retryable=True, error=type(exc).__name__)
    except URLError:
        return HttpSendResult(success=False, retryable=True, error="network_error")
    except OSError as exc:
        return HttpSendResult(success=False, retryable=True, error=type(exc).__name__)
