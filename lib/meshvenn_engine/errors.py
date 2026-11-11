"""Stable application errors; adapters decide their own transport envelopes."""
from __future__ import annotations


class EngineError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}
