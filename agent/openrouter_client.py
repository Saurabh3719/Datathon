"""
Real LLM-backed fallback via OpenRouter (https://openrouter.ai) -- a unified,
OpenAI-compatible API gateway to many model providers behind one API key.
Replaces the earlier Gemini-specific integration; same two-call design,
same safety guardrail, same response shape, different backend.

Plain `requests` HTTP calls, not a provider SDK -- OpenRouter's API is a
straightforward OpenAI-compatible REST endpoint, so a dedicated SDK isn't
needed and this avoids an extra dependency.

Two-call design:
  1. plan_with_llm(question) -- the model reads the question + schema and
     returns intent / keywords / confidence / SQL / visualization / ER
     mapping. No execution results exist yet at this point.
  2. summarize_with_llm(question, rows) -- a second, small call grounded in
     the ACTUAL query results, so the natural-language answer is
     data-grounded rather than a guess about what the results might contain.

Every SQL string returned is re-validated by safety.is_read_only() before it
ever touches the database -- this fallback is the highest-risk part of the
whole agent (an LLM, not a hand-vetted template), so the guardrail matters
here more than anywhere else in the codebase.

Requires OPENROUTER_API_KEY in the environment (a local .env file is loaded
automatically if present -- see .env.example; never commit a real key).
Unconfigured, is_configured() is False and app.py falls back to the
existing "no_match" behavior unchanged -- this module is strictly additive.
"""
import json
import os
import re
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from .safety import is_read_only

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, widely-available model with reliable JSON-mode support. Override
# via OPENROUTER_MODEL if this becomes unavailable (see openrouter.ai/models
# for current options, including free-tier models) -- same lesson learned
# from the earlier Gemini default going stale mid-project.
MODEL_NAME = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

SCHEMA_DESCRIPTION = """Tables:
- dim_merchants: merchant_id (PK), merchant_name, mcc, merchant_category, business_type, city, state, onboarding_date, merchant_status, declared_avg_ticket_size
- dim_customers: user_id (PK), full_name, city, state, monthly_income, occupation, signup_timestamp, kyc_status, risk_segment
- fact_transactions: txn_id (PK), timestamp, user_id (FK -> dim_customers.user_id), merchant_id (FK -> dim_merchants.merchant_id), amount, mcc, status ('SUCCESS','PENDING','FAILED')
- fact_chargebacks: complaint_id (PK), txn_id (FK -> fact_transactions.txn_id), user_id (FK -> dim_customers.user_id), merchant_id (FK -> dim_merchants.merchant_id), transaction_timestamp, reported_timestamp, bank_response_timestamp, reporting_delay_days, disputed_amount, reason_code, resolution_status ('CLOSED','IN_PROGRESS'), severity ('CRITICAL','HIGH','MEDIUM','LOW'), channel

Join rules:
- fact_transactions.merchant_id = dim_merchants.merchant_id
- fact_transactions.user_id = dim_customers.user_id
- fact_chargebacks.txn_id = fact_transactions.txn_id
- fact_chargebacks.user_id = dim_customers.user_id
- fact_chargebacks.merchant_id = dim_merchants.merchant_id

Database engine: SQLite. Boolean-style flag columns (e.g. utr_valid,
merchant_id_valid_fk) are stored as SQLite integers 0/1, not TEXT."""

SYSTEM_INSTRUCTION = f"""You are a text-to-SQL analyst for a UPI/FinTech fraud analytics SQLite database.

{SCHEMA_DESCRIPTION}

Rules:
- Output ONLY a single read-only SELECT statement (a leading WITH CTE clause is fine) inside the sql_query field. Never INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA, and never multiple statements separated by semicolons.
- Use explicit `JOIN ... ON` with table aliases for any cross-table query -- never an implicit/comma join.
- If the question mentions "amount" without saying whether it means transaction amount (fact_transactions.amount) or disputed/chargeback amount (fact_chargebacks.disputed_amount), set confidence_score below 0.9 to reflect that ambiguity.
- er_diagram_ascii should show the primary table and each joined table with its join condition, in the style: [table_a] <--(a.col = b.col)--> [table_b].
- confidence_score is your genuine estimate (0-1) of how well you understood the intent, not a fixed constant.

Respond with ONLY a single JSON object, no markdown code fences, no commentary before or after, matching exactly this shape:
{{
  "intent": "snake_case_label",
  "keywords_matched": ["..."],
  "confidence_score": 0.0,
  "sql_query": "SELECT ...;",
  "visualization": {{"type": "line|bar|pie|table|metric_card", "x_axis": "...", "y_axis": "...", "title": "..."}},
  "kpis_calculated": ["..."],
  "primary_table": "...",
  "joined_tables": ["..."],
  "join_conditions": ["..."],
  "variables_used": ["..."],
  "er_diagram_ascii": "...",
  "index_space_followups": ["...", "...", "..."]
}}
"""


def is_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
        # OpenRouter attribution headers (optional, but recommended by their
        # docs -- helps them route/rank apps, no effect on functionality).
        "X-Title": "UPI Fraud Analytics Agent (local)",
    }


def _extract_json(text: str) -> dict:
    """Some models wrap JSON in ```json fences despite instructions not to;
    strip that if present before parsing."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        text = m.group(1)
    return json.loads(text)


def _chat(messages: list, **extra) -> str:
    resp = requests.post(
        OPENROUTER_URL,
        headers=_headers(),
        json={"model": MODEL_NAME, "messages": messages, **extra},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def plan_with_llm(question: str) -> dict:
    """Returns a dict shaped like nlsql.match_intent()'s 'ok' result (plus
    source='openrouter'), or {'status': 'error', 'message': ...} if the
    call, its JSON, or the read-only safety check fails."""
    if not is_configured():
        return {"status": "error", "message": "OPENROUTER_API_KEY is not set."}

    try:
        content = _chat(
            [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": f"User question: {question}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        plan = _extract_json(content)
    except Exception as e:
        return {"status": "error", "message": f"OpenRouter request failed: {e}"}

    sql = plan.get("sql_query", "")
    if not is_read_only(sql):
        return {
            "status": "error",
            "message": "OpenRouter returned a query that failed the read-only safety check; refusing to execute it.",
            "sql": sql,
        }

    return {
        "status": "ok",
        "intent": plan.get("intent", "llm_generated"),
        "sql": sql,
        "viz": plan["visualization"],
        "followups": (plan.get("index_space_followups") or [])[:3],
        "keywords_matched": plan.get("keywords_matched", []),
        "confidence_score": float(plan.get("confidence_score", 0.5)),
        "er_mapping": {
            "kpis_calculated": plan.get("kpis_calculated", []),
            "primary_table": plan.get("primary_table", ""),
            "joined_tables": plan.get("joined_tables", []),
            "join_conditions": plan.get("join_conditions", []),
            "variables_fetched": plan.get("variables_used", []),
            "er_diagram_ascii": plan.get("er_diagram_ascii", ""),
        },
        "source": "openrouter",
        "model": MODEL_NAME,
    }


def summarize_with_llm(question: str, rows: list) -> str:
    """Second, small call grounded in the actual rows -- falls back to a
    generic summary if this call fails, so a single API hiccup doesn't take
    down an otherwise-successful query."""
    fallback = f"Query returned {len(rows)} row(s)." if rows else "The query returned no rows."
    if not is_configured():
        return fallback
    try:
        sample = rows[:20]
        content = _chat(
            [
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n"
                        f"Query result (JSON, up to 20 rows shown): {json.dumps(sample, default=str)}\n\n"
                        "Write one concise sentence that directly answers the question using these results. "
                        "Cite specific numbers/names from the data. No preamble, no restating the question."
                    ),
                }
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = content.strip()
        return text or fallback
    except Exception:
        return fallback
