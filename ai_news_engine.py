import os
import json
import sys
import news_engine

# ---------------------------------------------------------------------------
# ai_news_engine.py  --  local-model backed news analysis
#
# OpenAI has been permanently removed. Analysis now uses the project\'s
# local inference system (Ollama via llm_gateway) when available, or falls
# back to a rule-based neutral-score pass-through that keeps callers working.
# ---------------------------------------------------------------------------


def _rule_based_result(base):
    """Return a safe rule-based result when local model is unavailable."""
    return {
        **base,
        "ai_enabled": False,
        "ai_summary": "Local model unavailable. Using rules-based news scoring.",
        "ai_news_score": base.get("news_score", 0),
        "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
        "ai_error": "local_model_unavailable",
    }


def fetch_ai_news(symbol="AAPL", limit=8):
    """Fetch news and enrich with local-model AI analysis.

    Falls back to rule-based scoring (same shape, ai_enabled=False) if the
    local model (Ollama) is not reachable.
    """
    base = news_engine.fetch_news(symbol, limit)

    headlines = []
    for i, item in enumerate(base.get("news_items", [])[:limit], start=1):
        title = item.get("title", "")
        source = item.get("source", "")
        published = item.get("published", "")
        headlines.append(
            str(i) + ". Title: " + title + " | Source: " + source + " | Published: " + published
        )

    if not headlines:
        return _rule_based_result(base)

    headlines_text = "\n".join(headlines)
    prompt = (
        "Analyze the sentiment impact of these stock news headlines for ticker " + symbol + ".\n\n"
        "Return ONLY valid JSON with this exact schema:\n"
        "{\n"
        "  \"ai_news_score\": integer_from_-5_to_5,\n"
        "  \"ai_news_sentiment\": \"POSITIVE\" or \"NEGATIVE\" or \"NEUTRAL\",\n"
        "  \"ai_summary\": \"short summary max 3 sentences\"\n"
        "}\n\n"
        "News headlines:\n" + headlines_text
    )

    try:
        # Use the project\'s local inference gateway (Ollama)
        sys.path.insert(0, "/app")
        from backend.app.services.llm_gateway import llm_chat, LLMUnavailableError

        messages = [
            {"role": "system", "content": "You are a concise financial news sentiment analyst. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ]
        result = llm_chat(messages, temperature=0.2, max_tokens=400)
        text = result.get("content", "").strip()

        try:
            parsed = json.loads(text)
        except Exception:
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception:
                    parsed = {}
            else:
                parsed = {}

        return {
            **base,
            "ai_enabled": True,
            "ai_summary": parsed.get("ai_summary", ""),
            "ai_news_score": int(parsed.get("ai_news_score", base.get("news_score", 0))),
            "ai_news_sentiment": parsed.get("ai_news_sentiment", base.get("news_sentiment", "NEUTRAL")),
            "ai_error": None,
            "ai_provider": result.get("provider", "local"),
            "ai_model": result.get("model", "unknown"),
        }

    except Exception as exc:
        return {
            **base,
            "ai_enabled": False,
            "ai_summary": "Local AI unavailable. Using rules-based scoring.",
            "ai_news_score": base.get("news_score", 0),
            "ai_news_sentiment": base.get("news_sentiment", "NEUTRAL"),
            "ai_error": str(exc),
        }
