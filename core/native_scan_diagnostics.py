from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewScanDiagnostic:
    """Voxel retention measured immediately after one source projection."""

    view: str
    order_index: int
    before: int
    after: int

    def __post_init__(self) -> None:
        if not self.view:
            raise ValueError("A scan view name is required.")
        if self.order_index < 0:
            raise ValueError("View order index cannot be negative.")
        if self.before < 0 or self.after < 0:
            raise ValueError("Voxel counts cannot be negative.")
        if self.after > self.before:
            raise ValueError("Surviving voxels cannot exceed the preceding count.")

    @property
    def removed_count(self) -> int:
        return self.before - self.after

    @property
    def retained_fraction(self) -> float:
        return self.after / self.before if self.before else 0.0

    @property
    def status(self) -> str:
        if self.after == 0:
            return "empty"
        if self.order_index > 0 and self.removed_count * 10 >= self.before * 9:
            return "sharp-drop"
        return "ok"

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "view": self.view,
            "order_index": self.order_index,
            "before": self.before,
            "after": self.after,
            "removed_count": self.removed_count,
            "retained_fraction": self.retained_fraction,
            "status": self.status,
        }
