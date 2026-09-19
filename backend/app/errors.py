"""Uniform error shape for the API, per docs/architecture.md's error handling section.

Every error response looks like {"error": {"code": ..., "message": ..., "details": {...}}}.
Raise WorkbenchError anywhere in the app; the handler registered in main.py converts it.
"""

from __future__ import annotations


class WorkbenchError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)
