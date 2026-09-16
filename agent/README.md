# Text-to-SQL Agent — UPI Fraud & Merchant Risk Analytics

The "optional graph-first AI agent" mentioned in the dataset notes, built as
a **read-only, natural-language query agent** instead: a FastAPI backend over
a SQLite database, with a Streamlit UI. This is the concrete deliverable for
the dataset notes' "Example agent queries" list.

Two layers, tried in order:
1. **Local templates** (`agent/nlsql.py`) — ~21 hand-vetted, deterministic
   SQL templates. Zero cost, zero latency beyond the SQLite query itself, zero
   network call, no API key. This is the primary path and covers every
   question in the dataset notes.
2. **OpenRouter API fallback** (`agent/openrouter_client.py`) — only tried
   when a question doesn't match a local template. A real call through
   [OpenRouter](https://openrouter.ai) (a unified, OpenAI-compatible gateway
   to many model providers behind one API key) generates the SQL (and
   everything else in the response) for open-ended questions the fixed
   template set doesn't cover. Requires `OPENROUTER_API_KEY`; see
   "OpenRouter fallback" below. (An earlier version of this integration used
   Google's Gemini API directly; swapped to OpenRouter on request — same
   two-call design and safety guardrail, different backend.)

## Why template-first, not LLM-first

An actual LLM call means a network round-trip, an API key, and (small)
per-request cost. Templates give none of that overhead and, since they're
hand-vetted, every answer is reproducible and has already been checked for
correctness (see the cross-validation below) — something an LLM-generated
query can't guarantee on every run. Trying templates first means the ~21
already-covered questions stay fast, free, and 100%-reliable regardless of
whether OpenRouter is configured or reachable; the LLM only has to earn its
keep on the genuinely novel questions the templates don't cover.

## Architecture

```
data/cleaned/*.csv  --agent/build_db.py-->  agent/analytics.db (SQLite)
                                                     |
                                    agent/nlsql.py (question -> SQL template)
                                                     |
                no match --> agent/openrouter_client.py (question -> OpenRouter API -> SQL)
                                                     |
                                    agent/safety.py (read-only guardrail -- applied
                                                      to BOTH template and LLM SQL)
                                                     |
                                       agent/app.py (FastAPI: POST /ask)
                                                     |
                                  agent/frontend.py (Streamlit: chart + SQL + answer)
```

## Running it

```bash
python3 -m pip install -r requirements.txt   # fastapi, uvicorn, streamlit, plotly, requests (+ pandas, numpy already there)
python3 agent/build_db.py                    # builds agent/analytics.db from data/cleaned/*.csv
python3 -m uvicorn agent.app:app --port 8000 # from the repo root
```
In a second terminal:
```bash
python3 -m streamlit run agent/frontend.py
```
Open the Streamlit URL it prints (typically http://localhost:8501). The
sidebar lists every supported example question as a clickable button.

Or hit the API directly:
```bash
curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Which merchant has the highest chargeback count?"}'
```

Rebuild `analytics.db` any time `data/cleaned/*.csv` changes (rerun
`scripts/clean_pipeline.py` first if the underlying data changed).

## OpenRouter fallback (optional)

Enables open-ended coverage beyond the ~21 local templates via OpenRouter, a
single API that fronts many model providers. **Off by default** — nothing
changes unless you set a key.

```bash
cp .env.example .env
# edit .env, set OPENROUTER_API_KEY=<your key from https://openrouter.ai/keys>
```
`.env` is loaded automatically (via `python-dotenv`) and is gitignored —
never commit a real key. Restart `uvicorn` after setting it. Default model
is `openai/gpt-4o-mini` (cheap, reliable JSON mode); override with
`OPENROUTER_MODEL` in `.env` — see https://openrouter.ai/models for current
options, including free-tier models (filter by max price $0).

**What actually happens, two API calls per fallback question:**
1. `plan_with_llm(question)` sends the question + full schema/join rules to
   the model with a system prompt asking for a single JSON object
   (`response_format: {"type": "json_object"}`) containing intent, keywords,
   confidence, the SQL query, the visualization spec, and the E-R mapping
   (including `kpis_calculated` and an ASCII diagram). No results exist yet
   at this point — the model is reasoning about the question and the schema
   only.
2. The returned SQL is re-validated by `safety.is_read_only()` **before it
   ever touches the database** — this is the single highest-risk point in
   the whole agent (an LLM output, not a hand-vetted template), so the exact
   same guardrail that protects the template path applies here, not a
   weaker version of it. A query that fails this check is refused and
   surfaced as an error, never silently executed.
3. If the query is safe, it's executed locally (same `_run_query` as the
   template path) and `summarize_with_llm(question, rows)` makes a
   *second*, small call grounded in the actual result rows, so the
   natural-language answer cites real numbers instead of guessing what the
   data might say.

**Cost/network honesty:** every fallback question makes 1–2 real API calls
to OpenRouter (which itself bills through to whichever provider serves the
chosen model). The local template path never does, regardless of whether
`OPENROUTER_API_KEY` is set — check the `llm_context_extraction.source`
field (`"template"` or `"openrouter"`, plus `model` when it's the latter) in
any response, or the "answered by" badge in the Streamlit UI, to see which
path actually answered.

**Verification history, for transparency:** this integration went through
two backends during development. The first (Gemini, called directly)
confirmed real end-to-end request handling — a deliberately invalid key came
back as a proper `API_KEY_INVALID` error from Google's own endpoint, and a
default model that Google had since retired came back with a clear
"no longer available, use X instead" error, which is exactly the kind of
signal this design is built to surface rather than swallow. It was then
swapped to OpenRouter on request; re-verify the live generation path with
your own `OPENROUTER_API_KEY` the same way — ask a question outside the ~21
local templates and check `llm_context_extraction.source`. If a request
fails, the raw provider error is surfaced in `answer_summary`, so please
share that exact message if you hit one.

## Response format

```json
{
  "llm_context_extraction": {
    "intent": "rank_merchants_by_chargeback_count",
    "keywords_matched": ["chargeback", "merchant"],
    "confidence_score": 0.95,
    "source": "template",
    "model": null
  },
  "collapsible_suggested_answer": {
    "title": "Click to view detailed answer summary",
    "answer_summary": "Mukhopadhyay, Dua and Dada (MCH9291) has the highest chargeback count, with 42 disputes."
  },
  "er_relationship_mapping": {
    "kpis_calculated": ["Chargeback Count by Merchant"],
    "primary_table": "fact_chargebacks",
    "joined_tables": ["dim_merchants"],
    "join_conditions": ["fact_chargebacks.merchant_id = dim_merchants.merchant_id"],
    "variables_fetched": ["dim_merchants.merchant_id", "dim_merchants.merchant_name", "dim_merchants.merchant_category"],
    "er_diagram_ascii": "[fact_chargebacks] <--(fact_chargebacks.merchant_id = dim_merchants.merchant_id)--> [dim_merchants]"
  },
  "sql_query": "SELECT ... FROM ... WHERE ...;",
  "visualization": {"type": "line|bar|pie|table|metric_card", "x_axis": "...", "y_axis": "...", "title": "..."},
  "index_space_followups": ["...", "...", "..."],
  "rows": [ {"...": "..."}, ... ]
}
```
`source` is `"template"` for a local-template answer (`model` is `null`) or
`"openrouter"` for the LLM fallback (`model` names the exact OpenRouter model
that answered, e.g. `"openai/gpt-4o-mini"`).

**`rows`** (the actual query results) is the one addition beyond the
requested schema — a dashboard widget can't render `visualization: {type,
x_axis, y_axis, title}` into a chart without the underlying data, so the
field is required for "local dashboard widgets ... can render charts
dynamically" to actually work. `agent/frontend.py` is the reference
consumer.

`confidence_score` means something different depending on `source`. For
`"template"` answers it's a **fixed rule-based tier**, not a trained-model
probability: 0.95 for a matched phrase template (comfortably above the ">90%,
else clarify" bar), 0.5 for a detected-but-ambiguous question, 0.0 for no
match at all — there's no ML model in that path to calibrate a real
probability from, so a legible fixed tier is more honest than a fake one. See
`agent/nlsql.py`'s module docstring. For `"openrouter"` answers, it's the
model's own self-reported estimate (prompted to reflect genuine uncertainty,
e.g. dip below 0.9 for an ambiguous "amount") — a real, if imperfect, model
judgment rather than a fixed constant.

`keywords_matched` comes from a **separate** table-level keyword scan (the
literal rules in this prompt: chargeback/dispute/reason/severity/delay →
`fact_chargebacks`, transaction/payment/volume/status/utr →
`fact_transactions`, etc. — see `TABLE_KEYWORDS` in `nlsql.py`), independent
of the phrase-level matching that actually selects the SQL template. It's
descriptive only; it doesn't influence which query runs.

`er_relationship_mapping` is `null` for `ambiguous`/no-match responses —
there's no specific query to map when nothing resolved.

UI mapping (`agent/frontend.py`): `collapsible_suggested_answer` renders as a
`st.expander` (Streamlit's `<details>/<summary>` equivalent) whose collapsed
label is `title`; `index_space_followups` render in a **sidebar** "Follow-up
index" list of buttons, separate from the static example-questions list, one
click away from re-asking.

For `"successful vs failed transactions by day"`-style questions the result
has two value series (`success_count`, `failed_count`); `y_axis` is returned
as `"success_count, failed_count"` (comma-joined) since the spec's schema
only allows one y-axis string per response — `frontend.py` splits on the
comma and plots both series.

## Guardrails implemented

1. **Read-only**: `agent/safety.py` rejects anything that isn't a single,
   standalone `SELECT` (optionally with a leading `WITH` CTE) — no
   `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`ATTACH`/`PRAGMA`/etc., and no
   stacked statements (`;` mid-string). Applied to every template-generated
   query as defense in depth, and to any future LLM-generated query.
   `agent/app.py` also opens the SQLite connection itself in `mode=ro` (a
   second, connection-level enforcement layer).
2. **SQLite-safe date handling**: every template uses `DATE(timestamp)` for
   day-grouping — standard SQLite, works directly against the ISO-format
   timestamp strings the cleaning pipeline already produces.
3. **Explicit joins/aliases**: every cross-table query uses explicit
   `JOIN ... ON` with table aliases (see `nlsql.py`) — e.g. KYC-status
   breakdowns join `fact_transactions t` to `dim_customers cu` on `user_id`
   explicitly, never an implicit/comma join.
4. **Ambiguity handling**: a question containing "amount" with no
   qualifying word (`transaction`, `txn`, `dispute`, `chargeback`,
   `disputed`) and no template match returns a clarifying question instead
   of guessing — `fact_transactions.amount` and
   `fact_chargebacks.disputed_amount` are different tables with very
   different totals. Try `"show me the amount by day"` vs `"show total
   transaction amount by day"` to see the difference.
5. **Follow-ups**: every successful match includes exactly 2
   `suggested_followups`, schema-aware (they reference real columns/tables).

## Supported questions

All 12 from the dataset notes' "Example agent queries," plus the remaining
"Example dashboard questions" / "Expected business metrics" that hadn't been
covered elsewhere yet:

- Show daily transaction volume trend.
- Show total transaction amount by merchant category.
- Compare successful vs failed transactions by day.
- Which merchant has the highest chargeback count?
- Which merchant category has the highest disputed amount?
- Show chargeback reason distribution.
- Show top 10 users by disputed amount.
- Show average transaction value trend over time.
- Which KYC status has the highest transaction amount?
- Compare chargebacks by severity level.
- Show disputes reported after 7 days.
- Which merchant has the highest chargeback-to-transaction ratio?
- Top merchants by disputed amount
- High-risk merchants with repeated disputes
- High-risk users with repeated disputes
- Merchants with sudden transaction spikes (suspicious transaction clusters)
- Transactions missing UTR or having invalid UTR formats
- Dispute rate by merchant category
- Pending transaction rate
- Failed transaction rate
- Average transaction value

Phrasing doesn't need to match exactly — matching is substring/phrase-based
(see `_score()` in `nlsql.py`), so reasonable variations work too (e.g.
"most disputes merchant", "which merchant has the most chargebacks").
Anything else returns a graceful "not supported yet" response listing the
options above, rather than a wrong guess.

## Correctness check

Every template was run end-to-end and cross-checked against the numbers
already published in `reports/business_metrics_summary.md` (produced
independently by the pandas-based `scripts/compute_metrics.py`). They agree
exactly, e.g.:
- Highest chargeback count: Mukhopadhyay, Dua and Dada (MCH9291), 42 disputes — matches.
- Highest CB-to-txn ratio: Tak-Wali (MCH8779), 566.7% — matches.
- Failed rate 7.8%, pending rate 24.1%, avg transaction value ₹12,488.63 — all match.
