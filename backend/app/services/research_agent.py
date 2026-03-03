"""
Research Agent
Fetches external risk signals for the borrower entity:
  - Company news via NewsAPI
  - MCA filings (directors, charges) via CompData API or mock
  - eCourts pending cases via Surepass API or mock
Gracefully skips any source where the API key is missing.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
SUREPASS_BASE = "https://kyc-api.surepass.io/api/v1"
COMPDATA_BASE = "https://api.compdata.io/v1"


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    sentiment: str = "neutral"   # positive | neutral | negative


@dataclass
class MCAData:
    company_name: str = ""
    cin: str = ""
    directors: list = field(default_factory=list)
    charges: list = field(default_factory=list)
    date_of_incorporation: str = ""
    paid_up_capital: float = 0.0
    status: str = ""


@dataclass
class CourtCase:
    case_number: str
    court: str
    status: str
    year: str
    party: str = ""


@dataclass
class ResearchResult:
    news_items: list[NewsItem] = field(default_factory=list)
    news_risk_score: float = 0.0       # 0–1 (1 = high risk)
    news_summary: str = ""

    mca_data: Optional[MCAData] = None
    mca_risk_score: float = 0.0
    mca_flags: list[str] = field(default_factory=list)

    court_cases: list[CourtCase] = field(default_factory=list)
    legal_risk_score: float = 0.0
    legal_summary: str = ""

    overall_research_risk: float = 0.0


# ---- Sentiment heuristic ----
NEGATIVE_KEYWORDS = [
    "fraud", "scam", "default", "bankrupt", "npa", "closure", "penalty",
    "insolvency", "nclt", "seized", "arrested", "cheating", "money laundering",
    "investigation", "raided", "cancelled", "suspended", "wound up",
]
POSITIVE_KEYWORDS = ["profit", "expansion", "award", "growth", "export", "listed"]


def _score_sentiment(text: str) -> str:
    lo = text.lower()
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in lo)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in lo)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


# ---- NewsAPI ----
async def _fetch_news(company_name: str) -> list[NewsItem]:
    if not settings.NEWSAPI_KEY:
        logger.info("NEWSAPI_KEY not set — skipping news fetch")
        return []
    params = {
        "q": company_name,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": settings.NEWSAPI_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(NEWSAPI_BASE, params=params)
            r.raise_for_status()
            articles = r.json().get("articles", [])
            items = []
            for a in articles[:5]:
                sentiment = _score_sentiment(
                    (a.get("title") or "") + " " + (a.get("description") or "")
                )
                items.append(NewsItem(
                    title=a.get("title", ""),
                    source=a.get("source", {}).get("name", ""),
                    published_at=a.get("publishedAt", ""),
                    url=a.get("url", ""),
                    sentiment=sentiment,
                ))
            return items
    except Exception as e:
        logger.warning(f"NewsAPI error: {e}")
        return []


def _news_risk_score(items: list[NewsItem]) -> tuple[float, str]:
    if not items:
        return 0.0, "No recent news found."
    neg = sum(1 for i in items if i.sentiment == "negative")
    ratio = neg / len(items)
    score = min(ratio * 1.2, 1.0)
    summary = f"{neg}/{len(items)} news items carry negative sentiment. "
    if neg > 0:
        summary += "Topics: " + "; ".join(
            i.title[:60] for i in items if i.sentiment == "negative"
        )
    return round(score, 3), summary


# ---- MCA (CompData mock or real) ----
async def _fetch_mca(company_name: str, cin: Optional[str]) -> Optional[MCAData]:
    if not settings.COMPDATA_API_KEY:
        logger.info("COMPDATA_API_KEY not set — returning mock MCA data")
        return MCAData(company_name=company_name, cin=cin or "UNKNOWN", status="Active")
    headers = {"Authorization": f"Bearer {settings.COMPDATA_API_KEY}"}
    query = cin if cin else company_name
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{COMPDATA_BASE}/company/{query}", headers=headers)
            r.raise_for_status()
            d = r.json()
            return MCAData(
                company_name=d.get("name", company_name),
                cin=d.get("cin", ""),
                directors=d.get("directors", []),
                charges=d.get("charges", []),
                date_of_incorporation=d.get("date_of_incorporation", ""),
                paid_up_capital=float(d.get("paid_up_capital", 0)),
                status=d.get("status", ""),
            )
    except Exception as e:
        logger.warning(f"CompData API error: {e}")
        return MCAData(company_name=company_name, status="Unavailable")


def _mca_risk(mca: Optional[MCAData]) -> tuple[float, list[str]]:
    if not mca:
        return 0.0, []
    flags = []
    score = 0.0
    if mca.charges:
        flags.append(f"{len(mca.charges)} charge(s) registered against company")
        score += min(len(mca.charges) * 0.1, 0.4)
    if mca.status and mca.status.lower() not in ("active", ""):
        flags.append(f"Company status: {mca.status}")
        score += 0.3
    return min(score, 1.0), flags


# ---- eCourts (Surepass or mock) ----
async def _fetch_ecourts(company_name: str) -> list[CourtCase]:
    if not settings.SUREPASS_API_KEY:
        logger.info("SUREPASS_API_KEY not set — skipping eCourts lookup")
        return []
    headers = {"Authorization": f"Bearer {settings.SUREPASS_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{SUREPASS_BASE}/court-case-search",
                json={"name": company_name},
                headers=headers,
            )
            r.raise_for_status()
            cases = r.json().get("data", {}).get("cases", [])
            return [
                CourtCase(
                    case_number=c.get("case_number", ""),
                    court=c.get("court", ""),
                    status=c.get("status", ""),
                    year=c.get("year", ""),
                    party=c.get("party_name", ""),
                )
                for c in cases[:10]
            ]
    except Exception as e:
        logger.warning(f"Surepass eCourts error: {e}")
        return []


# ---- Main orchestrator ----
async def run_research_agent(
    company_name: str,
    cin: Optional[str] = None,
) -> ResearchResult:
    import asyncio

    news_task = asyncio.create_task(_fetch_news(company_name))
    mca_task = asyncio.create_task(_fetch_mca(company_name, cin))
    court_task = asyncio.create_task(_fetch_ecourts(company_name))

    news_items = await news_task
    mca_data = await mca_task
    court_cases = await court_task

    news_risk, news_summary = _news_risk_score(news_items)
    mca_risk, mca_flags = _mca_risk(mca_data)

    legal_risk = min(len(court_cases) * 0.15, 1.0)
    legal_summary = (
        f"{len(court_cases)} court case(s) found."
        if court_cases
        else "No court cases found."
    )

    overall = round((news_risk * 0.3 + mca_risk * 0.4 + legal_risk * 0.3), 3)

    return ResearchResult(
        news_items=news_items,
        news_risk_score=news_risk,
        news_summary=news_summary,
        mca_data=mca_data,
        mca_risk_score=mca_risk,
        mca_flags=mca_flags,
        court_cases=court_cases,
        legal_risk_score=legal_risk,
        legal_summary=legal_summary,
        overall_research_risk=overall,
    )


def research_to_dict(result: ResearchResult) -> dict:
    mca = result.mca_data
    return {
        "news": [
            {"title": n.title, "source": n.source, "sentiment": n.sentiment, "url": n.url}
            for n in result.news_items
        ],
        "news_risk_score": result.news_risk_score,
        "news_summary": result.news_summary,
        "mca": {
            "company_name": mca.company_name if mca else "",
            "cin": mca.cin if mca else "",
            "status": mca.status if mca else "",
            "directors": mca.directors if mca else [],
            "charges": mca.charges if mca else [],
        } if mca else {},
        "mca_risk_score": result.mca_risk_score,
        "mca_flags": result.mca_flags,
        "court_cases": [
            {"case_number": c.case_number, "court": c.court, "status": c.status, "year": c.year}
            for c in result.court_cases
        ],
        "legal_risk_score": result.legal_risk_score,
        "legal_summary": result.legal_summary,
        "overall_research_risk": result.overall_research_risk,
    }
