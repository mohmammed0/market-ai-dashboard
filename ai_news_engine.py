import os
import json
from openai import OpenAI, RateLimitError
import news_engine


def fetch_ai_news(symbol="AAPL", limit=8):
    base = news_engine.fetch_news(symbol, limit)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {
            **base,
            "ai_enabled": False,
            "ai_summary": "OPENAI_API_KEY not set. Fallback to rules-based news scoring.",
            "ai_news_score": base.get("news_score", 0),
            "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
            "ai_error": "missing_api_key"
        }

    headlines = []
    for i, item in enumerate(base.get("news_items", [])[:limit], start=1):
        headlines.append(
            f"{i}. Title: {item.get('title','')} | Source: {item.get('source','')} | Published: {item.get('published','')}"
        )

    prompt = f"""
Analyze the sentiment impact of these stock news headlines for ticker {symbol}.

Return ONLY valid JSON with this exact schema:
{{
  "ai_news_score": integer_from_-5_to_5,
  "ai_news_sentiment": "POSITIVE" or "NEGATIVE" or "NEUTRAL",
  "ai_summary": "short summary max 3 sentences"
}}

News headlines:
{chr(10).join(headlines)}
""".strip()

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model="gpt-5.4",
            input=prompt
        )

        text = response.output_text.strip()

        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {
                "ai_news_score": base.get("news_score", 0),
                "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
                "ai_summary": text[:800]
            }

        return {
            **base,
            "ai_enabled": True,
            "ai_summary": parsed.get("ai_summary", ""),
            "ai_news_score": int(parsed.get("ai_news_score", base.get("news_score", 0))),
            "ai_news_sentiment": parsed.get("ai_news_sentiment", base.get("news_sentiment", "NEUTRAL")),
            "ai_error": None
        }

    except RateLimitError as e:
        return {
            **base,
            "ai_enabled": False,
            "ai_summary": "AI temporarily unavailable: insufficient quota or rate limit. Using rules-based scoring.",
            "ai_news_score": base.get("news_score", 0),
            "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
            "ai_error": str(e)
        }

    except Exception as e:
        return {
            **base,
            "ai_enabled": False,
            "ai_summary": "AI request failed. Using rules-based scoring.",
            "ai_news_score": base.get("news_score", 0),
            "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
            "ai_error": str(e)
        }
