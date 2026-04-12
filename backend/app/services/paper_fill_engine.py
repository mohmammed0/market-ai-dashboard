"""Paper trading fill simulation engine.

Computes deterministic, auditable simulated fills for paper trades.

Models
------
Slippage
    Market orders pay a directional slippage in basis points.
    BUY: fill price increases (trader pays more than the reference).
    SELL: fill price decreases (trader receives less than the reference).
    Limit orders have zero slippage (they fill at limit price or better).

Spread
    If live bid/ask is available: BUY fills at ask, SELL fills at bid.
    Fallback when no live quotes: apply half the configured spread_bps
    symmetrically against the trader (BUY pays more, SELL receives less).

Fee
    Flat per-share commission applied to the filled quantity.
    Configurable via MARKET_AI_PAPER_FEE_PER_SHARE env var.

Partial fills
    Deterministic rule: market orders for more than PAPER_PARTIAL_FILL_THRESHOLD
    shares fill at PAPER_PARTIAL_FILL_RATIO (default 90%).  All others fill fully.
    Limit orders always fill fully when the condition is met.
    No randomness is introduced; the same inputs always produce the same output.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.config import (
    PAPER_FEE_PER_SHARE,
    PAPER_PARTIAL_FILL_RATIO,
    PAPER_PARTIAL_FILL_THRESHOLD,
    PAPER_SLIPPAGE_BPS,
    PAPER_SPREAD_BPS,
)


@dataclass
class FillResult:
    """All components of a simulated paper fill — fully auditable."""

    reference_price: float      # raw market price before any adjustment
    spread_adj: float           # half-spread cost: positive for BUY, negative for SELL
    slippage_adj: float         # directional slippage: positive for BUY, negative for SELL
    fee_amount: float           # total commission for the fill (qty × fee_per_share)
    fill_price: float           # final simulated execution price = ref + spread + slippage
    filled_quantity: float      # shares actually filled (may be < requested)
    fill_ratio: float           # filled_quantity / requested_quantity  (0.0 – 1.0)
    is_partial: bool            # True when fill_ratio < 1.0
    order_type: str             # "market" | "limit"
    side: str                   # "BUY" | "SELL"

    def to_audit_dict(self) -> dict:
        """Return a dict suitable for inclusion in an audit-event payload."""
        return {
            "reference_price": round(self.reference_price, 4),
            "spread_adj": round(self.spread_adj, 6),
            "slippage_adj": round(self.slippage_adj, 6),
            "fee_amount": round(self.fee_amount, 4),
            "fill_price": round(self.fill_price, 4),
            "filled_quantity": round(self.filled_quantity, 4),
            "fill_ratio": round(self.fill_ratio, 6),
            "is_partial": self.is_partial,
            "order_type": self.order_type,
            "side": self.side,
        }

    def to_notes_str(self) -> str:
        """Compact human-readable summary for trade/order notes columns."""
        requested_qty = round(self.filled_quantity / self.fill_ratio) if self.fill_ratio > 0 else 0
        return (
            f"ref={self.reference_price:.4f}"
            f" | spread={self.spread_adj:+.4f}"
            f" | slip={self.slippage_adj:+.4f}"
            f" | fill={self.fill_price:.4f}"
            f" | qty={self.filled_quantity:.0f}/{requested_qty:.0f}"
            f" | fee={self.fee_amount:.4f}"
        )


def compute_fill(
    side: str,
    quantity: float,
    reference_price: float,
    order_type: str = "market",
    limit_price: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    slippage_bps: float = PAPER_SLIPPAGE_BPS,
    spread_bps: float = PAPER_SPREAD_BPS,
    fee_per_share: float = PAPER_FEE_PER_SHARE,
    partial_fill_threshold: float = PAPER_PARTIAL_FILL_THRESHOLD,
    partial_fill_ratio: float = PAPER_PARTIAL_FILL_RATIO,
) -> FillResult:
    """Compute a deterministic simulated fill for a paper trade.

    Parameters
    ----------
    side : str
        "BUY" / "LONG" / "OPEN_LONG" for a buy-side fill;
        "SELL" / "SHORT" / "OPEN_SHORT" / "CLOSE_LONG" for sell-side.
    quantity : float
        Requested share count.
    reference_price : float
        Mid-market or last-trade reference price.
    order_type : str
        "market" or "limit".
    limit_price : float | None
        Required for limit orders.
    bid : float | None
        Live bid price (used for SELL spread; falls back to formula).
    ask : float | None
        Live ask price (used for BUY spread; falls back to formula).
    slippage_bps … partial_fill_ratio
        Override config defaults for testing.
    """
    normalized_side = str(side or "BUY").strip().upper()
    is_buy = normalized_side in {"BUY", "LONG", "OPEN_LONG"}
    normalized_order_type = str(order_type or "market").strip().lower()

    qty = max(float(quantity or 0.0), 0.0)
    ref = max(float(reference_price or 0.0), 0.0)

    # ------------------------------------------------------------------
    # Partial fill — deterministic size rule
    # Large market orders fill at partial_fill_ratio; all others fill fully.
    # Limit orders always fill fully when the price condition is met.
    # ------------------------------------------------------------------
    if normalized_order_type == "market" and qty > partial_fill_threshold:
        fill_ratio = float(partial_fill_ratio)
    else:
        fill_ratio = 1.0

    filled_qty = round(qty * fill_ratio, 4)

    # ------------------------------------------------------------------
    # Spread adjustment
    # ------------------------------------------------------------------
    if normalized_order_type == "market":
        if is_buy:
            raw_ask = float(ask) if ask is not None and float(ask) > 0 else None
            spread_adj = (raw_ask - ref) if raw_ask is not None else (ref * (spread_bps / 10000.0) / 2.0)
        else:
            raw_bid = float(bid) if bid is not None and float(bid) > 0 else None
            spread_adj = (raw_bid - ref) if raw_bid is not None else -(ref * (spread_bps / 10000.0) / 2.0)
    else:
        # Limit fills at limit_price; spread_adj captures distance from mid.
        spread_adj = (float(limit_price) - ref) if limit_price is not None else 0.0

    # ------------------------------------------------------------------
    # Slippage — directional, basis-points, market orders only
    # ------------------------------------------------------------------
    if normalized_order_type == "market":
        raw_slip = ref * (slippage_bps / 10000.0)
        slippage_adj = raw_slip if is_buy else -raw_slip
    else:
        slippage_adj = 0.0

    # ------------------------------------------------------------------
    # Fill price
    # ------------------------------------------------------------------
    fill_price = max(ref + spread_adj + slippage_adj, 0.0001)

    # ------------------------------------------------------------------
    # Fee
    # ------------------------------------------------------------------
    fee_amount = round(filled_qty * fee_per_share, 4)

    return FillResult(
        reference_price=round(ref, 4),
        spread_adj=round(spread_adj, 6),
        slippage_adj=round(slippage_adj, 6),
        fee_amount=fee_amount,
        fill_price=round(fill_price, 4),
        filled_quantity=round(filled_qty, 4),
        fill_ratio=round(fill_ratio, 6),
        is_partial=fill_ratio < 1.0,
        order_type=normalized_order_type,
        side=normalized_side,
    )
