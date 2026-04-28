from __future__ import annotations


class DomainError(Exception):
    """Base exception for domain and use case failures."""


class UnsupportedEventTypeError(DomainError):
    """Raised when an event type is not accepted by policy."""


class EventValidationError(DomainError):
    """Raised when an event is structurally invalid for ingestion."""
