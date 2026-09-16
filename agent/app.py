"""
FastAPI Text-to-SQL agent for the UPI Fraud & Merchant Risk Analytics
dataset. Local SQLite database + deterministic query templates as the
primary path (no network, no API key, no cost); a real OpenRouter API call
as the fallback for questions that don't match a local template (see
agent/openrouter_client.py and agent/README.md for the tradeoffs).

Run:  python3 -m uvicorn agent.app:app --reload --port 8000   (from repo root)
Then: POST http://localhost:8000/ask   {"question": "..."}
See agent/README.md for the full list of supported questions and how to
enable the OpenRouter fallback (OPENROUTER_API_KEY).
"""
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import openrouter_client as llm_client
from .nlsql import match_intent
from .safety import is_read_only

DB_PATH = Path(__file__).resolve().parent / "analytics.db"

app = FastAPI(
    title="UPI Fraud Analytics -- Text-to-SQL Agent",
    description="Local, read-only natural-language query agent over the cleaned Track 1 star schema, with an optional OpenRouter-backed LLM fallback.",
    version="1.3.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local desktop tool -- no auth/session boundary to protect
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


class LlmContextExtraction(BaseModel):
    intent: str
    keywords_matched: list[str] = []
    confidence_score: float
    source: str = "template"  # "template" (local, deterministic) or "openrouter" (real API call)
    model: Optional[str] = None  # the specific model used, when source == "openrouter"


class CollapsibleSuggestedAnswer(BaseModel):
    title: str = "Click to view detailed answer summary"
    answer_summary: str


class ErRelationshipMapping(BaseModel):
    kpis_calculated: list[str] = []
    primary_table: str
    joined_tables: list[str] = []
    join_conditions: list[str] = []
    variables_fetched: list[str] = []
    er_diagram_ascii: str = ""


class Visualization(BaseModel):
    type: str
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    title: str


class AskResponse(BaseModel):
    llm_context_extraction: LlmContextExtraction
    collapsible_suggested_answer: CollapsibleSuggestedAnswer
    er_relationship_mapping: Optional[ErRelationshipMapping] = None
    sql_query: Optional[str] = None
    visualization: Optional[Visualization] = None
    index_space_followups: list[str] = []
    rows: list[dict] = []  # actual query results -- needed by any real chart widget, beyond the base spec


def _run_query(sql: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _no_match_response(result: dict) -> AskResponse:
    examples = result["examples"]
    hint = (
        "Set OPENROUTER_API_KEY to also try this question against an LLM for open-ended coverage."
        if not llm_client.is_configured()
        else "The OpenRouter fallback was tried and also could not answer this -- see below."
    )
    return AskResponse(
        llm_context_extraction=LlmContextExtraction(
            intent="unrecognized",
            keywords_matched=result["keywords_matched"],
            confidence_score=result["confidence_score"],
            source="template",
        ),
        collapsible_suggested_answer=CollapsibleSuggestedAnswer(
            answer_summary=(
                "I don't have a supported query for that yet -- this agent uses a fixed set of vetted "
                f"templates rather than an LLM, so only known question shapes are covered. {hint} "
                "Try one of the example questions below."
            )
        ),
        er_relationship_mapping=None,
        sql_query=None,
        visualization=None,
        index_space_followups=examples[:3],
        rows=[],
    )


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    result = match_intent(req.question)

    if result["status"] == "ambiguous":
        return AskResponse(
            llm_context_extraction=LlmContextExtraction(
                intent=result["intent"],
                keywords_matched=result["keywords_matched"],
                confidence_score=result["confidence_score"],
                source="template",
            ),
            collapsible_suggested_answer=CollapsibleSuggestedAnswer(answer_summary=result["clarification"]),
            er_relationship_mapping=None,
            sql_query=None,
            visualization=None,
            index_space_followups=result["suggested_followups"],
            rows=[],
        )

    if result["status"] == "no_match":
        # Local templates are the primary, free, deterministic path.
        # OpenRouter is only ever tried once that path has nothing -- see
        # agent/README.md for why this order, not the reverse.
        if llm_client.is_configured():
            plan = llm_client.plan_with_llm(req.question)
            if plan["status"] == "ok":
                rows = _run_query(plan["sql"])
                summary = llm_client.summarize_with_llm(req.question, rows)
                return AskResponse(
                    llm_context_extraction=LlmContextExtraction(
                        intent=plan["intent"],
                        keywords_matched=plan["keywords_matched"],
                        confidence_score=plan["confidence_score"],
                        source="openrouter",
                        model=plan.get("model"),
                    ),
                    collapsible_suggested_answer=CollapsibleSuggestedAnswer(answer_summary=summary),
                    er_relationship_mapping=ErRelationshipMapping(**plan["er_mapping"]),
                    sql_query=plan["sql"],
                    visualization=Visualization(**plan["viz"]),
                    index_space_followups=plan["followups"],
                    rows=rows,
                )
            # OpenRouter was configured but failed (bad key, network, unsafe
            # SQL, malformed JSON, etc.) -- fall through to the honest
            # no_match response, but surface what went wrong instead of
            # hiding it.
            fallback = _no_match_response(result)
            fallback.collapsible_suggested_answer.answer_summary += f" (OpenRouter fallback error: {plan['message']})"
            return fallback
        return _no_match_response(result)

    sql = result["sql"]
    if not is_read_only(sql):
        # Should never happen for a template-generated query; this check
        # matters far more for the LLM path above, but applies uniformly.
        return AskResponse(
            llm_context_extraction=LlmContextExtraction(
                intent=result["intent"], keywords_matched=result["keywords_matched"], confidence_score=0.0, source="template"
            ),
            collapsible_suggested_answer=CollapsibleSuggestedAnswer(
                answer_summary="This query was blocked because it did not pass the read-only safety check."
            ),
            er_relationship_mapping=ErRelationshipMapping(**result["er_mapping"]),
            sql_query=sql,
            visualization=None,
            index_space_followups=[],
            rows=[],
        )

    rows = _run_query(sql)
    summary = result["summary_fn"](rows)
    return AskResponse(
        llm_context_extraction=LlmContextExtraction(
            intent=result["intent"],
            keywords_matched=result["keywords_matched"],
            confidence_score=result["confidence_score"],
            source="template",
        ),
        collapsible_suggested_answer=CollapsibleSuggestedAnswer(answer_summary=summary),
        er_relationship_mapping=ErRelationshipMapping(**result["er_mapping"]),
        sql_query=sql,
        visualization=Visualization(**result["viz"]),
        index_space_followups=result["followups"],
        rows=rows,
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "openrouter_fallback_configured": llm_client.is_configured(),
        "openrouter_model": llm_client.MODEL_NAME if llm_client.is_configured() else None,
    }


@app.get("/examples")
def examples():
    from .nlsql import _example_questions

    return {"examples": _example_questions()}
