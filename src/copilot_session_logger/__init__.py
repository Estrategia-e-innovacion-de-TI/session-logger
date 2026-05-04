"""Deprecated Python implementation of the local Copilot session logger.

The active hook/logger implementation lives in hooks/session-logger.sh and lib/.
This package is kept temporarily for compatibility with existing installs.
"""

from .schema import SUPPORTED_EVENTS

__all__ = ["SUPPORTED_EVENTS", "__deprecated__", "__version__"]

__version__ = "0.1.0"
__deprecated__ = True
