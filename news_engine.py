import requests
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from news_intelligence import classify_news_item, headline_signature


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
    "dividend increase",
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
    "stock sale",
]

EVENT_BIAS = {
    "earnings": 1.0,
    "analyst": 0.5,
    "corporate_action": 0.3,
    "mna": 0.6,
    "product": 0.3,
    "legal_regulatory": -0.4,
    "macro": 0.0,
    "general": 0.0,
}


def _score_text(text):
    t = text.lower()
    score = 0.0

    for phrase in POSITIVE_PHRASES:
        if phrase in t:
            score += 1.0

    for phrase in NEGATIVE_PHRASES:
        if phrase in t:
            score -= 1.0

    if "too late to consider" in t:
        score -= 1.0
    if "recent share price pullback" in t:
        score -= 1.0

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


def _scored_item(symbol, title, source, link, pub_date, *, relation="fresh", novelty_score=1.0):
    intelligence = classify_news_item(symbol, title, source, novelty_score=novelty_score, relation=relation)
    raw_score = _score_text(f"{title} {source}")
    adjusted_score = raw_score + EVENT_BIAS.get(intelligence["event_type"], 0.0)
    adjusted_score *= 0.7 + (intelligence["source_quality_score"] * 0.3)
    adjusted_score *= 0.75 + (intelligence["relevance_score"] * 0.25)
    adjusted_score *= 0.65 + (intelligence["novelty_score"] * 0.35)
    score = int(round(adjusted_score))
    sentiment = _label_score(score)
    return {
        "title": title,
        "source": source,
        "published": pub_date,
        "sentiment": sentiment,
        "news_score": score,
        "link": link,
        **intelligence,
    }


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
    seen_exact = set()
    seen_semantic = {}

    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = _parse_date(item.findtext("pubDate"))
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else "Unknown"

        exact_key = (title.lower(), source.lower(), pub_date.lower())
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)

        semantic_key = headline_signature(title)
        scored = _scored_item(symbol, title, source, link, pub_date)
        previous = seen_semantic.get(semantic_key)
        if previous:
            previous_rank = (
                previous["source_quality_score"],
                previous["relevance_score"],
                len(previous["title"]),
            )
            current_rank = (
                scored["source_quality_score"],
                scored["relevance_score"],
                len(scored["title"]),
            )
            if current_rank > previous_rank:
                replacement = _scored_item(symbol, title, source, link, pub_date, relation="event_update", novelty_score=0.55)
                news_items[previous["index"]] = replacement
                seen_semantic[semantic_key] = {"index": previous["index"], **replacement}
            continue

        seen_semantic[semantic_key] = {"index": len(news_items), **scored}
        news_items.append(scored)
        if len(news_items) >= limit:
            break

    for row in news_items:
        total_score += row["news_score"]
        if row["sentiment"] == "POSITIVE":
            positive_count += 1
        elif row["sentiment"] == "NEGATIVE":
            negative_count += 1
        else:
            neutral_count += 1

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
        "news_items": news_items,
    }
