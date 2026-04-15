"""Trade notification service — sends alerts via Telegram.

Sends notifications for:
- New BUY/SELL signals
- Trade executions (open/close)
- Daily portfolio summary
- Auto-trading cycle results
- Trailing stop triggers
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def notify_signal(symbol: str, signal: str, confidence: float, price: float, reasoning: str = ""):
    """Notify about a new trading signal."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return

        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}.get(signal, "⚪")
        conf_bar = "█" * int(confidence / 10) + "░" * (10 - int(confidence / 10))

        msg = (
            f"{emoji} <b>إشارة {signal}</b>\n"
            f"📊 {symbol} — ${price:,.2f}\n"
            f"📈 الثقة: {confidence:.0f}% [{conf_bar}]\n"
        )
        if reasoning:
            msg += f"💡 {reasoning[:200]}\n"

        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_signal failed: %s", exc)


def notify_trade_executed(symbol: str, side: str, qty: float, price: float,
                          order_id: str = "", mode: str = "paper",
                          pnl: float | None = None):
    """Notify about a trade execution."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return

        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>تنفيذ صفقة</b>\n"
            f"📊 {symbol} — {side.upper()}\n"
            f"📦 الكمية: {qty:.0f} سهم\n"
            f"💰 السعر: ${price:,.2f}\n"
            f"🏦 الوضع: {mode}\n"
        )
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            msg += f"{pnl_emoji} الربح/الخسارة: ${pnl:,.2f}\n"
        if order_id:
            msg += f"🆔 {order_id}\n"

        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_trade_executed failed: %s", exc)


def notify_auto_trading_summary(symbols_scanned: int, buy_count: int, sell_count: int,
                                 hold_count: int, errors: int, top_buys: list[dict] = None):
    """Notify about auto-trading cycle results."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return

        msg = (
            f"🤖 <b>دورة التداول التلقائي</b>\n"
            f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔍 الأسهم المفحوصة: {symbols_scanned}\n"
            f"🟢 شراء: {buy_count}\n"
            f"🔴 بيع: {sell_count}\n"
            f"⚪ انتظار: {hold_count}\n"
        )
        if errors:
            msg += f"⚠️ أخطاء: {errors}\n"

        if top_buys:
            msg += f"\n<b>أفضل فرص الشراء:</b>\n"
            for b in top_buys[:5]:
                msg += f"  • {b.get('symbol')} — ثقة {b.get('confidence', 0):.0f}% — ${b.get('price', 0):,.2f}\n"

        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_auto_trading_summary failed: %s", exc)


def notify_trailing_stop(symbol: str, side: str, trigger_price: float,
                          entry_price: float, pnl: float):
    """Notify when trailing stop is triggered."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return

        emoji = "📉" if pnl < 0 else "📈"
        msg = (
            f"🛑 <b>وقف خسارة متحرك</b>\n"
            f"📊 {symbol} — {side}\n"
            f"💰 سعر الدخول: ${entry_price:,.2f}\n"
            f"🎯 سعر التفعيل: ${trigger_price:,.2f}\n"
            f"{emoji} الربح/الخسارة: ${pnl:,.2f}\n"
        )
        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_trailing_stop failed: %s", exc)


def notify_daily_summary(portfolio_value: float, total_pnl: float,
                          open_positions: int, trades_today: int):
    """Send end-of-day portfolio summary."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return

        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        msg = (
            f"📋 <b>ملخص يومي</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💼 قيمة المحفظة: ${portfolio_value:,.2f}\n"
            f"{pnl_emoji} الربح/الخسارة: ${total_pnl:,.2f}\n"
            f"📊 الصفقات المفتوحة: {open_positions}\n"
            f"🔄 صفقات اليوم: {trades_today}\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        )
        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_daily_summary failed: %s", exc)


def notify_market_open():
    """Notify that market has opened and auto-trading is active."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return
        msg = (
            f"🔔 <b>السوق مفتوح</b>\n"
            f"🤖 التداول التلقائي نشط\n"
            f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}\n"
        )
        send_telegram_message(msg)
    except Exception as exc:
        logger.debug("notify_market_open failed: %s", exc)
