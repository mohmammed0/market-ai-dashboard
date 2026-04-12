import requests
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime


POSITIVE_PHRASES = [
    "beats earnings",
    "beat earnings",
    "strong earnings",
    "raises guidance",
    "record revenue",
    "record profit",
    "price target raised",
    "upgraded",
    "upgrade",
    "bullish",
    "buy rating",
    "outperform",
    "surges",
    "jumps",
    "growth",
    "profit",
    "profits",
    "rebound",
    "recovery",
    "expands",
    "buyback",
    "dividend increase"
]

NEGATIVE_PHRASES = [
    "misses earnings",
    "missed earnings",
    "cuts guidance",
    "guidance cut",
    "price target cut",
    "downgraded",
    "downgrade",
    "bearish",
    "sell rating",
    "underperform",
    "falls",
    "drops",
    "decline",
    "declines",
    "loss",
    "losses",
    "lawsuit",
    "investigation",
    "antitrust",
    "warning",
    "risk",
    "risks",
    "pullback",
    "reduced holdings",
    "sells $",
    "stock sale"
]


def _score_text(text):
    t = text.lower()
    score = 0

    for phrase in POSITIVE_PHRASES:
        if phrase in t:
            score += 1

    for phrase in NEGATIVE_PHRASES:
        if phrase in t:
            score -= 1

    if "too late to consider" in t:
        score -= 1
    if "recent share price pullback" in t:
        score -= 1
    if "turned 50 years old" in t:
        score += 0

    return score


def _label_score(score):
    if score >= 1:
        return "POSITIVE"
    if score <= -1:
        return "NEGATIVE"
    return "NEUTRAL"


def _parse_date(pub_date):
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return pub_date or ""


def fetch_news(symbol="AAPL", limit=10):
    symbol = symbol.upper().strip()
    query = urllib.parse.quote(symbol + " stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    response = requests.get(url, timeout=20)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_items = []
    total_score = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0

    for item in items[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = _parse_date(item.findtext("pubDate"))
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else "Unknown"

        text_for_score = f"{title} {source}"
        score = _score_text(text_for_score)
        sentiment = _label_score(score)
        total_score += score

        if sentiment == "POSITIVE":
            positive_count += 1
        elif sentiment == "NEGATIVE":
            negative_count += 1
        else:
            neutral_count += 1

        news_items.append({
            "title": title,
            "source": source,
            "published": pub_date,
            "sentiment": sentiment,
            "news_score": score,
            "link": link
        })

    if total_score >= 2:
        overall_sentiment = "POSITIVE"
    elif total_score <= -2:
        overall_sentiment = "NEGATIVE"
    else:
        overall_sentiment = "NEUTRAL"

    return {
        "symbol": symbol,
        "news_score": total_score,
        "news_sentiment": overall_sentiment,
        "articles_count": len(news_items),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "neutral_count": neutral_count,
        "news_items": news_items
    }
