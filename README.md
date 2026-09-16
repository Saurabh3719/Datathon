# Track 1 — UPI Fraud Ring & Merchant Analytics

TransOrg AgentIQ Datathon, Track 1 (FinTech & BFSI). This repo takes the raw,
deliberately-messy synthetic dataset through a documented cleaning pipeline
into an analytics-ready star schema (`data/cleaned/`), then a fraud / dispute /
merchant-risk dashboard built on top of it.

**Note on the raw source files:** the original 4 files (in particular the KYC
file, which carries unmasked PAN/Aadhaar-shaped values) are intentionally
**not** included in this public repository — only the cleaned output, which
masks both, is published. See `reports/cleaning_mapping_reference.md` for why.
To reproduce the pipeline from scratch, place the 4 original files
(`track1_upi_transactions.csv`, `track1_kyc_records.csv`,
`track1_merchants_master.csv`, `track1_chargebacks.json`) into `data/raw/`
yourself before running the scripts below.

## Repo layout

```
data/
  raw/                        (not published — see note above) place the 4 original source files here
  cleaned/                    output of the cleaning pipeline (the data model)
    dim_customers.csv
    dim_merchants.csv
    fact_transactions.csv
    fact_chargebacks.csv
scripts/
  clean_pipeline.py           raw -> cleaned star schema
  compute_metrics.py          cleaned tables -> reports/ + dashboard/data.json
  build_dashboard.py          dashboard/data.json + template.html -> dashboard/index.html
  build_powerbi_project.py    cleaned tables -> powerbi/ (native Power BI Project)
reports/
  data_quality_report.md      what was cleaned, what was dropped/imputed/flagged, and why
  business_metrics_summary.md all KPIs from the notes, computed and narrated
  cleaning_mapping_reference.md   every normalization lookup table, for audit
dashboard/
  index.html                  the dashboard (open directly in a browser, no server needed; fully offline)
  data.json                   the pre-aggregated data it's built from
  chart.umd.min.js            vendored locally so the dashboard needs no internet connection
  powerbi_guide.md            star schema + DAX measures, if rebuilding by hand in Power BI Desktop
powerbi/
  UPI_Fraud_Analytics.pbip    native Power BI Project - open directly in Power BI Desktop
  README.md                   full writeup: data processing, every KPI/measure, every visual, every filter
agent/
  build_db.py                 cleaned tables -> agent/analytics.db (SQLite)
  nlsql.py                    the text-to-SQL template engine (question -> SQL, fully local)
  openrouter_client.py        optional OpenRouter API fallback for questions beyond the local templates
  safety.py                   read-only SQL guardrail (applied to both template and LLM SQL)
  app.py                      FastAPI backend (POST /ask)
  frontend.py                 Streamlit UI (chart + SQL + natural-language answer)
  README.md                   architecture, guardrails, supported questions, correctness check
.env.example                   copy to .env and add OPENROUTER_API_KEY to enable the OpenRouter fallback
requirements.txt
```

## Reproducing the pipeline

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/clean_pipeline.py       # writes data/cleaned/*.csv + reports/data_quality_report.md
python3 scripts/compute_metrics.py      # writes reports/business_metrics_summary.md + dashboard/data.json
python3 scripts/build_dashboard.py      # writes dashboard/index.html
python3 scripts/build_powerbi_project.py  # writes powerbi/ (native Power BI Project)
python3 agent/build_db.py               # writes agent/analytics.db (for the text-to-SQL agent)
```

Then open `dashboard/index.html` in any browser — it's fully self-contained
and works offline (data and Chart.js are both bundled locally, no CDN). For
the native Power BI report, open `powerbi/UPI_Fraud_Analytics.pbip` in Power
BI Desktop — see `powerbi/README.md` for the full data model, every KPI, every
visual, and every filter with the reasoning behind it. For the natural-
language query agent (the "optional graph-first AI agent" from the dataset
notes, built as a local text-to-SQL assistant instead), see `agent/README.md`
— `python3 -m uvicorn agent.app:app --port 8000` then
`python3 -m streamlit run agent/frontend.py`.

## Cleaning approach, in one paragraph

Every messy field the dataset notes call out (ID formats, currency-formatted
amounts, six-plus timestamp formats, inconsistent status/category spellings,
PAN/Aadhaar formats, MCC codes, chargeback reason codes) is standardized by
`scripts/clean_pipeline.py` using explicit, documented rules
(`reports/cleaning_mapping_reference.md`). Rows are **only** dropped when a
stable identifier cannot be recovered at all, or when they're exact duplicates.
Everything else — negative amounts, unparseable values, orphaned foreign keys,
logically-impossible timestamp sequences — is standardized and flagged with an
explicit boolean column instead of silently discarded, per the evaluation note
that blanket-dropping messy rows should be penalized. Full before/after counts
for every transformation are in `reports/data_quality_report.md`.

## Headline finding: this dataset's biggest signal is in the joins, not the charts

Only **32.4%** of transactions reference a `user_id` that exists in the KYC
master, and only **48.2%** reference a `merchant_id` that exists in the
merchant master (`reports/business_metrics_summary.md`, "Join / Data-Quality
Integrity"). That's far beyond what you'd expect from incidental data-entry
noise — it reads as a deliberate feature of this "fraud ring" dataset: a large
share of platform activity has **no linkable identity or merchant record at
all**. Rather than restricting analysis to the matched subset (which would
understate exposure) or dropping unmatched rows (which the evaluation notes
explicitly discourage), every fact table carries `*_valid_fk` flags so this gap
is itself a first-class, measured finding.

On top of that, a handful of specific merchants and users carry chargeback
volume wildly out of proportion to their recorded transaction history — e.g. a
merchant with 42 disputes against 3 recorded transactions, a user with 14
disputes and no KYC record at all. See the "Fraud-Ring Spotlight" section of
the dashboard.

## Business metrics delivered

All metrics listed in the dataset notes are computed in
`reports/business_metrics_summary.md` and visualized in `dashboard/index.html`:
transaction volume/value/success/failed/pending rates, chargeback count/amount/
ratio (by count and by amount), dispute rate by merchant category, high-risk
merchants and users, KYC completion/rejection rate, average dispute reporting
delay, merchant category performance, and suspicious same-day transaction
clusters cross-referenced against subsequent disputes.

## The optional AI agent

The dataset notes mention an optional "graph-first AI agent." Built instead
as a read-only text-to-SQL agent (`agent/`) — see `agent/README.md`. Not
graph-based. Two layers: a fixed set of vetted local SQL templates as the
primary, free, zero-network path (covers all 12 of the dataset notes'
"Example agent queries" plus the remaining example dashboard
questions/business metrics), and an optional real OpenRouter API fallback
for open-ended questions beyond that set (off unless you set
`OPENROUTER_API_KEY`).
