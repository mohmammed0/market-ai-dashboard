from fastapi import APIRouter, HTTPException

from backend.app.schemas import AINewsAnalyzeRequest
from backend.app.services.ai_news_analyst import analyze_news
from backend.app.services.llm_gateway import get_llm_status, LLMUnavailableError


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status():
    return get_llm_status()


@router.post("/news/analyze")
def analyze_news_endpoint(payload: AINewsAnalyzeRequest):
    result = analyze_news(payload)
    if not result.get("success", False):
        raise HTTPException(status_code=502, detail=result.get("error", "LLM analysis failed")) from None
    return result
