from __future__ import annotations

from pydantic import BaseModel, Field


class ExposureSnapshot(BaseModel):
    gross_exposure_pct: float = 0.0
    net_exposure_pct: float = 0.0
    symbol_weights: dict[str, float] = Field(default_factory=dict)
    sector_weights: dict[str, float] = Field(default_factory=dict)


__all__ = ["ExposureSnapshot"]

