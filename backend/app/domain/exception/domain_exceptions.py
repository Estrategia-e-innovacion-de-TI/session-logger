from __future__ import annotations


class DomainError(Exception):
    """Base exception for domain and application policy failures."""


class EventValidationError(DomainError):
    """Raised when a Copilot event breaks domain ingestion rules."""


class UnsupportedEventTypeError(DomainError):
    """Raised when event_type is outside the accepted policy."""

