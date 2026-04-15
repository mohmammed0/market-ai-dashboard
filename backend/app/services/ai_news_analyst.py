from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from backend.app.schemas import AINewsAnalysisResponse, AINewsAnalyzeRequest
from backend.app.services.llm_gateway import llm_chat, LLMUnavailableError, get_llm_status


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are a conservative financial news analyst for a market research platform.
Only use the text and context provided in the request.
Do not invent prices, earnings dates, analyst ratings, valuation levels, or market reactions that were not provided.
Separate direct facts from likely implications and uncertainty.
If the news is mixed, vague, stale, or not clearly material, prefer NEUTRAL with lower confidence.
Keep the result concise, practical, and readable by traders and researchers.
Affected tickers must be limited to explicitly mentioned or strongly implied public-market tickers.
Analyst notes should clearly signal uncertainty when the evidence is incomplete.
""".strip()


def _build_user_prompt(payload: AINewsAnalyzeRequest) -> str:
    lines = [
        "Analyze the following market news input and return only the requested JSON schema.",
        "",
        f"Primary symbol: {str(payload.symbol or '').strip() or 'Not provided'}",
        f"Market context: {str(payload.market_context or '').strip() or 'Not provided'}",
        "",
    ]
    if str(payload.headline or "").strip():
        lines.extend(["Headline:", str(payload.headline).strip(), ""])
    if str(payload.article_text or "").strip():
        lines.extend(["Article text:", str(payload.article_text).strip(), ""])
    if payload.items:
        lines.append("Additional items:")
        for item in payload.items:
            item_text = str(item or "").strip()
            if item_text:
                lines.append(f"- {item_text}")
        lines.append("")
    lines.extend([
        "Important:",
        "- Confidence is a 0-100 score.",
        "- Be cautious when the text is incomplete or ambiguous.",
        "- Do not state or imply price moves unless they were explicitly given.",
    ])
    return "\n".join(lines).strip()


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _coerce_analysis_payload(payload_json: dict | None) -> dict:
    data = dict(payload_json or {})
    try:
        confidence = float(data.get("confidence", 0.0))
        if 0.0 <= confidence <= 1.0:
            data["confidence"] = round(confidence * 100.0, 2)
    except Exception:
        pass
    for field_name in ("bullish_factors", "bearish_factors", "risks", "catalysts", "affected_tickers"):
        value = data.get(field_name)
        if not isinstance(value, list):
            data[field_name] = []
    return data


def analyze_news(payload: AINewsAnalyzeRequest) -> dict:
    """Analyze news using the configured local AI runtime."""
    user_prompt = _build_user_prompt(payload)

    # Add JSON schema instruction to user prompt for non-structured providers
    json_instruction = """
Respond ONLY with valid JSON matching this exact schema (no extra fields):
{
  "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence": <integer 0-100>,
  "impact_horizon": "INTRADAY" or "SHORT_TERM" or "MEDIUM_TERM" or "LONG_TERM",
  "summary": "<1-2 sentence summary>",
  "bullish_factors": ["<factor>"],
  "bearish_factors": ["<factor>"],
  "risks": ["<risk>"],
  "catalysts": ["<catalyst>"],
  "affected_tickers": ["<TICKER>"],
  "analyst_note": "<brief analyst commentary on confidence and uncertainty>"
}
"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt + "\n\n" + json_instruction},
    ]

    try:
        result = llm_chat(messages, temperature=0.2, max_tokens=800)
        content = result.get("content", "")
        # Parse JSON from response
        parsed = _extract_json(content)
        parsed = _coerce_analysis_payload(parsed)

        try:
            response = AINewsAnalysisResponse.model_validate(parsed)
            return {
                "success": True,
                "provider": result.get("provider", "unknown"),
                "model": result.get("model", "unknown"),
                **response.model_dump(),
            }
        except ValidationError as exc:
            logger.error(
                "AI News Analyst response schema mismatch for symbol=%s | raw=%r | errors=%s",
                payload.symbol,
                content[:600],
                exc.errors(),
            )
            raise LLMUnavailableError("LLM response did not match the expected schema.") from exc
    except LLMUnavailableError as exc:
        return {"success": False, "error": str(exc), "provider": "none"}
    except Exception as exc:
        logger.exception("AI News Analyst unexpected failure for symbol=%s", payload.symbol)
        return {"success": False, "error": str(exc), "provider": "unknown"}


# Backward compatibility alias for older imports.
analyze_news_with_openai = analyze_news
