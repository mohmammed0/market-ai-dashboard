"""Feature-engine domain service facade."""

from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation

__all__ = ["compute_market_breadth", "compute_sector_rotation"]
