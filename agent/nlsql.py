"""
Text-to-SQL engine for the UPI Fraud & Merchant Risk Analytics agent.

Deliberately template-based, not LLM-based: every query in the dataset
notes' "Example agent queries" and "Example dashboard questions" lists is a
known, fixed analytical question against a known schema. Matching natural-
language phrasing to one of a fixed set of vetted, parameterized SQL
templates is what actually makes "fully local desktop setup ... no cloud
dependency" true, rather than aspirational -- there's no LLM call, no API
key, and no network access anywhere in this path. Every template is a single
read-only SELECT, additionally re-validated by safety.is_read_only() before
execution as defense in depth.

Confidence scoring is a fixed rule-based tier, not a trained classifier
probability: a matched phrase template scores 0.95 (>= the 90% bar), a
low-confidence table-keyword-only match scores below 0.9 and triggers
clarification instead of a speculative join, and no keyword match at all
scores 0.0. This is intentionally conservative/legible rather than a real
ML confidence estimate -- there's no model here to calibrate one from.

If you want true open-ended natural-language coverage beyond the ~21
supported questions here, the natural extension point is an LLM-backed
fallback in app.py when match_intent() returns "no_match" -- deliberately
not built here, since that would reintroduce the cloud dependency this
design avoids for the core path. See agent/README.md.
"""
import re
from dataclasses import dataclass, field
from typing import Callable


def _fmt_inr(v) -> str:
    if v is None:
        return "₹0"
    return f"₹{v:,.2f}"


def _pct(n, d) -> str:
    if not d:
        return "0.0%"
    return f"{(n / d) * 100:.1f}%"


# Section-2 style table-level keyword rules, used only to populate
# nlp_extracted_context.keywords_matched / help build the E-R mapping --
# independent of the phrase-level intent matching below, which is what
# actually selects the SQL template.
TABLE_KEYWORDS = {
    "fact_chargebacks": ["chargeback", "dispute", "reason", "severity", "delay"],
    "fact_transactions": ["transaction", "payment", "volume", "status", "utr"],
    "dim_merchants": ["merchant", "mcc", "business type", "ticket size"],
    "dim_customers": ["customer", "user", "kyc", "risk segment", "income", "occupation"],
}


def extract_table_keywords(question: str) -> list:
    """Returns every section-2 keyword literally present in the question, in
    rule-table order. Purely descriptive (feeds the API response); does not
    influence SQL generation."""
    q = question.lower()
    matched = []
    for kws in TABLE_KEYWORDS.values():
        for kw in kws:
            if kw in q and kw not in matched:
                matched.append(kw)
    return matched


@dataclass
class Intent:
    name: str
    keywords: list
    sql: str
    viz: dict
    followups: list
    thought: str
    summary_fn: Callable[[list], str]
    primary_table: str = ""
    joined_tables: list = field(default_factory=list)
    join_conditions: list = field(default_factory=list)
    variables_fetched: list = field(default_factory=list)
    kpis_calculated: list = field(default_factory=list)

    def er_diagram_ascii(self) -> str:
        if not self.joined_tables:
            return f"[{self.primary_table}] (standalone -- no joins)"
        parts = [f"[{self.primary_table}]"]
        for jt, cond in zip(self.joined_tables, self.join_conditions):
            parts.append(f"<--({cond})--> [{jt}]")
        return " ".join(parts)

    def er_mapping(self) -> dict:
        return {
            "kpis_calculated": self.kpis_calculated,
            "primary_table": self.primary_table,
            "joined_tables": self.joined_tables,
            "join_conditions": self.join_conditions,
            "variables_fetched": self.variables_fetched,
            "er_diagram_ascii": self.er_diagram_ascii(),
        }


def _s_daily_volume(rows):
    if not rows:
        return "No transaction data found."
    total = sum(r["txn_count"] for r in rows)
    peak = max(rows, key=lambda r: r["txn_count"])
    return (
        f"Across {len(rows)} days ({rows[0]['txn_date']} to {rows[-1]['txn_date']}), "
        f"{total:,} transactions were recorded. The peak day was {peak['txn_date']} "
        f"with {peak['txn_count']:,} transactions."
    )


def _s_amount_by_category(rows):
    if not rows:
        return "No transaction data found."
    top = rows[0]
    return (
        f"'{top['merchant_category']}' leads with {_fmt_inr(top['total_amount'])} in total "
        f"transaction amount, across {len(rows)} merchant categories."
    )


def _s_success_vs_failed(rows):
    if not rows:
        return "No transaction data found."
    total_success = sum(r["success_count"] for r in rows)
    total_failed = sum(r["failed_count"] for r in rows)
    return (
        f"Over {len(rows)} days: {total_success:,} successful vs {total_failed:,} failed "
        f"transactions ({_pct(total_failed, total_success + total_failed)} failure rate overall)."
    )


def _s_top_merchant_cb_count(rows):
    if not rows:
        return "No chargeback data found."
    top = rows[0]
    return f"{top['merchant_name']} ({top['merchant_id']}) has the highest chargeback count, with {top['chargeback_count']:,} disputes."


def _s_category_disputed_amount(rows):
    if not rows:
        return "No chargeback data found."
    top = rows[0]
    return f"'{top['merchant_category']}' has the highest disputed amount at {_fmt_inr(top['total_disputed'])}."


def _s_reason_distribution(rows):
    if not rows:
        return "No chargeback data found."
    top = rows[0]
    total = sum(r["count"] for r in rows)
    return f"'{top['reason_code']}' is the most common dispute reason ({top['count']:,} of {total:,} chargebacks, {_pct(top['count'], total)})."


def _s_top_users_disputed(rows):
    if not rows:
        return "No chargeback data found."
    top = rows[0]
    name = top.get("full_name") or top["user_id"]
    return f"{name} ({top['user_id']}) has the highest disputed amount at {_fmt_inr(top['total_disputed'])}, across the top {len(rows)} users shown."


def _s_avg_value_trend(rows):
    if not rows:
        return "No transaction data found."
    avg_overall = sum(r["avg_amount"] for r in rows) / len(rows)
    return f"Average transaction value across the window hovers around {_fmt_inr(avg_overall)} per day (mean of daily averages)."


def _s_kyc_highest_amount(rows):
    if not rows:
        return "No data found."
    top = rows[0]
    return f"Customers with KYC status '{top['kyc_status']}' account for the highest transaction amount: {_fmt_inr(top['total_amount'])}."


def _s_severity(rows):
    if not rows:
        return "No chargeback data found."
    parts = ", ".join(f"{r['severity']}: {r['count']:,}" for r in rows)
    return f"Chargebacks by severity -- {parts}."


def _s_delayed_disputes(rows):
    if not rows:
        return "No chargebacks were reported more than 7 days after the transaction."
    return f"{len(rows):,} chargebacks were reported more than 7 days after the transaction (showing up to 200)."


def _s_highest_ratio(rows):
    if not rows:
        return "No merchant met the minimum transaction/dispute thresholds for a reliable ratio."
    top = rows[0]
    return (
        f"{top['merchant_name']} ({top['merchant_id']}) has the highest chargeback-to-transaction ratio "
        f"at {_pct(top['cb_count'], top['txn_count'])} ({top['cb_count']} disputes / {top['txn_count']} transactions)."
    )


def _s_top_merchants_disputed_amount(rows):
    if not rows:
        return "No chargeback data found."
    top = rows[0]
    return f"{top['merchant_name']} has the highest disputed amount at {_fmt_inr(top['total_disputed'])} across {top['cb_count']} disputes."


def _s_high_risk_merchants(rows):
    if not rows:
        return "No merchants have 2 or more chargebacks."
    return f"{len(rows):,} merchants have 2 or more chargebacks (repeat-dispute / high-risk merchants). Top: {rows[0]['merchant_name']} with {rows[0]['cb_count']} disputes."


def _s_high_risk_users(rows):
    if not rows:
        return "No users have 2 or more chargebacks."
    top = rows[0]
    name = top.get("full_name") or top["user_id"]
    no_kyc = sum(1 for r in rows if not r.get("kyc_status"))
    extra = f" {no_kyc} of them have no KYC record at all." if no_kyc else ""
    return f"{len(rows):,} users have 2 or more chargebacks (repeat-dispute / high-risk users). Top: {name} with {top['cb_count']} disputes.{extra}"


def _s_merchant_spikes(rows):
    if not rows:
        return "No merchant-day had 2 or more transactions."
    return f"{len(rows):,} merchant-days had 2+ transactions (anomalous vs. this population's ~1-txn/90-day norm). Top: merchant {rows[0]['merchant_id']} on {rows[0]['txn_date']} with {rows[0]['txn_count']} transactions."


def _s_missing_invalid_utr(rows):
    if not rows:
        return "No transactions have a missing or invalid UTR."
    return f"{len(rows):,} transactions have a missing or invalid UTR (showing up to 200)."


def _s_dispute_rate_by_category(rows):
    if not rows:
        return "No data found."
    top = max(rows, key=lambda r: r["dispute_rate"] if r["txn_count"] else 0)
    return f"'{top['merchant_category']}' has the highest dispute rate at {_pct(top['cb_count'], top['txn_count'])} ({top['cb_count']} disputes / {top['txn_count']} transactions)."


def _s_pending_rate(rows):
    if not rows:
        return "No transaction data found."
    r = rows[0]
    return f"Pending transaction rate: {_pct(r['pending_count'], r['total_count'])} ({r['pending_count']:,} of {r['total_count']:,})."


def _s_failed_rate(rows):
    if not rows:
        return "No transaction data found."
    r = rows[0]
    return f"Failed transaction rate: {_pct(r['failed_count'], r['total_count'])} ({r['failed_count']:,} of {r['total_count']:,})."


def _s_avg_txn_value(rows):
    if not rows:
        return "No transaction data found."
    return f"Average transaction value: {_fmt_inr(rows[0]['avg_amount'])}."


INTENTS = [
    Intent(
        "aggregate_daily_txn_volume",
        ["daily transaction volume", "transaction volume trend", "transactions per day", "daily volume", "volume trend"],
        "SELECT DATE(timestamp) AS txn_date, COUNT(*) AS txn_count, SUM(amount) AS txn_amount "
        "FROM fact_transactions GROUP BY DATE(timestamp) ORDER BY txn_date;",
        {"type": "line", "x_axis": "txn_date", "y_axis": "txn_count", "title": "Daily Transaction Volume Trend"},
        ["What is the daily transaction value trend?", "Which day had the most failed transactions?", "Compare successful vs failed transactions by day."],
        "Group fact_transactions by calendar date, counting rows and summing amount per day.",
        _s_daily_volume,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.timestamp", "fact_transactions.amount"],
        kpis_calculated=["Daily Transaction Count", "Daily Transaction Amount"],
    ),
    Intent(
        "aggregate_amount_by_merchant_category",
        ["amount by merchant category", "total transaction amount by category", "transaction amount by category"],
        "SELECT m.merchant_category, SUM(t.amount) AS total_amount, COUNT(*) AS txn_count "
        "FROM fact_transactions t JOIN dim_merchants m ON t.merchant_id = m.merchant_id "
        "GROUP BY m.merchant_category ORDER BY total_amount DESC;",
        {"type": "bar", "x_axis": "merchant_category", "y_axis": "total_amount", "title": "Total Transaction Amount by Merchant Category"},
        ["Which merchant category has the highest disputed amount?", "What's the dispute rate by merchant category?", "Show top merchants by disputed amount."],
        "Join fact_transactions to dim_merchants on merchant_id, sum amount grouped by merchant_category.",
        _s_amount_by_category,
        primary_table="fact_transactions",
        joined_tables=["dim_merchants"],
        join_conditions=["fact_transactions.merchant_id = dim_merchants.merchant_id"],
        variables_fetched=["dim_merchants.merchant_category", "fact_transactions.amount"],
        kpis_calculated=["Total Transaction Amount by Category"],
    ),
    Intent(
        "compare_success_vs_failed_by_day",
        ["successful vs failed", "success vs fail", "compare successful and failed", "success vs failed transactions"],
        "SELECT DATE(timestamp) AS txn_date, "
        "SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS success_count, "
        "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed_count "
        "FROM fact_transactions GROUP BY DATE(timestamp) ORDER BY txn_date;",
        {"type": "line", "x_axis": "txn_date", "y_axis": "success_count, failed_count", "title": "Successful vs Failed Transactions by Day"},
        ["What is the overall failed transaction rate?", "Show the failed-transaction rate by hour.", "Show daily transaction volume trend."],
        "Group by date, using conditional SUM (CASE WHEN) to split status into success/failed counts per day.",
        _s_success_vs_failed,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.timestamp", "fact_transactions.status"],
        kpis_calculated=["Success Count by Day", "Failed Count by Day"],
    ),
    Intent(
        "rank_merchants_by_chargeback_count",
        ["highest chargeback count", "most chargebacks", "merchant has the highest chargeback count", "most disputes merchant"],
        "SELECT m.merchant_id, m.merchant_name, m.merchant_category, COUNT(*) AS chargeback_count "
        "FROM fact_chargebacks c JOIN dim_merchants m ON c.merchant_id = m.merchant_id "
        "GROUP BY m.merchant_id, m.merchant_name, m.merchant_category ORDER BY chargeback_count DESC LIMIT 10;",
        {"type": "bar", "x_axis": "merchant_name", "y_axis": "chargeback_count", "title": "Top Merchants by Chargeback Count"},
        ["Which merchant has the highest chargeback-to-transaction ratio?", "Show top merchants by disputed amount.", "Show high-risk merchants with repeated disputes."],
        "Join fact_chargebacks to dim_merchants on merchant_id, count disputes per merchant, sort descending, top 10.",
        _s_top_merchant_cb_count,
        primary_table="fact_chargebacks",
        joined_tables=["dim_merchants"],
        join_conditions=["fact_chargebacks.merchant_id = dim_merchants.merchant_id"],
        variables_fetched=["dim_merchants.merchant_id", "dim_merchants.merchant_name", "dim_merchants.merchant_category"],
        kpis_calculated=["Chargeback Count by Merchant"],
    ),
    Intent(
        "rank_categories_by_disputed_amount",
        ["category has the highest disputed amount", "merchant category which has the highest disputed amount", "disputed amount by category"],
        "SELECT m.merchant_category, SUM(c.disputed_amount) AS total_disputed, COUNT(*) AS cb_count "
        "FROM fact_chargebacks c JOIN dim_merchants m ON c.merchant_id = m.merchant_id "
        "GROUP BY m.merchant_category ORDER BY total_disputed DESC;",
        {"type": "bar", "x_axis": "merchant_category", "y_axis": "total_disputed", "title": "Disputed Amount by Merchant Category"},
        ["What's the dispute rate by merchant category?", "Show chargeback reason distribution.", "Show total transaction amount by merchant category."],
        "Join fact_chargebacks to dim_merchants on merchant_id, sum disputed_amount grouped by merchant_category.",
        _s_category_disputed_amount,
        primary_table="fact_chargebacks",
        joined_tables=["dim_merchants"],
        join_conditions=["fact_chargebacks.merchant_id = dim_merchants.merchant_id"],
        variables_fetched=["dim_merchants.merchant_category", "fact_chargebacks.disputed_amount"],
        kpis_calculated=["Total Disputed Amount by Category"],
    ),
    Intent(
        "aggregate_disputes_by_reason",
        ["chargeback reason distribution", "reason code distribution", "dispute reason distribution"],
        "SELECT reason_code, COUNT(*) AS count FROM fact_chargebacks GROUP BY reason_code ORDER BY count DESC;",
        {"type": "pie", "x_axis": "reason_code", "y_axis": "count", "title": "Chargeback Reason Distribution"},
        ["Show dispute severity distribution.", "Compare chargebacks by severity level.", "Which merchant has the highest chargeback count?"],
        "Group fact_chargebacks by reason_code and count rows per category.",
        _s_reason_distribution,
        primary_table="fact_chargebacks",
        variables_fetched=["fact_chargebacks.reason_code"],
        kpis_calculated=["Chargeback Count by Reason Code"],
    ),
    Intent(
        "rank_users_by_disputed_amount",
        ["top 10 users by disputed amount", "top users by disputed amount", "users by disputed amount"],
        "SELECT c.user_id, cu.full_name, SUM(c.disputed_amount) AS total_disputed, COUNT(*) AS cb_count "
        "FROM fact_chargebacks c LEFT JOIN dim_customers cu ON c.user_id = cu.user_id "
        "GROUP BY c.user_id, cu.full_name ORDER BY total_disputed DESC LIMIT 10;",
        {"type": "table", "x_axis": "user_id", "y_axis": "total_disputed", "title": "Top 10 Users by Disputed Amount"},
        ["Which of these users have no KYC record?", "Show high-risk users with repeated disputes.", "Which KYC status has the highest transaction amount?"],
        "Left join fact_chargebacks to dim_customers on user_id (LEFT so users with no KYC record still appear), sum disputed_amount, top 10.",
        _s_top_users_disputed,
        primary_table="fact_chargebacks",
        joined_tables=["dim_customers"],
        join_conditions=["fact_chargebacks.user_id = dim_customers.user_id"],
        variables_fetched=["dim_customers.full_name", "fact_chargebacks.disputed_amount"],
        kpis_calculated=["Total Disputed Amount by User"],
    ),
    Intent(
        "aggregate_avg_txn_value_trend",
        ["average transaction value trend", "average transaction value over time", "avg transaction value trend"],
        "SELECT DATE(timestamp) AS txn_date, AVG(amount) AS avg_amount FROM fact_transactions "
        "GROUP BY DATE(timestamp) ORDER BY txn_date;",
        {"type": "line", "x_axis": "txn_date", "y_axis": "avg_amount", "title": "Average Transaction Value Trend"},
        ["What is the overall average transaction value?", "Show daily transaction volume trend.", "Show total transaction amount by merchant category."],
        "Group fact_transactions by date, taking AVG(amount) per day.",
        _s_avg_value_trend,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.timestamp", "fact_transactions.amount"],
        kpis_calculated=["Average Transaction Value by Day"],
    ),
    Intent(
        "rank_kyc_status_by_txn_amount",
        ["kyc status has the highest transaction amount", "kyc status highest amount", "which kyc status"],
        "SELECT cu.kyc_status, SUM(t.amount) AS total_amount, COUNT(*) AS txn_count "
        "FROM fact_transactions t JOIN dim_customers cu ON t.user_id = cu.user_id "
        "GROUP BY cu.kyc_status ORDER BY total_amount DESC;",
        {"type": "bar", "x_axis": "kyc_status", "y_axis": "total_amount", "title": "Transaction Amount by KYC Status"},
        ["What's the KYC completion rate?", "Show the dispute rate by KYC status.", "Show top 10 users by disputed amount."],
        "Join fact_transactions to dim_customers on user_id, sum amount grouped by kyc_status. Note: only 32.4% of transactions have a matching KYC record -- unmatched transactions are excluded here since kyc_status is only known for matched customers.",
        _s_kyc_highest_amount,
        primary_table="fact_transactions",
        joined_tables=["dim_customers"],
        join_conditions=["fact_transactions.user_id = dim_customers.user_id"],
        variables_fetched=["dim_customers.kyc_status", "fact_transactions.amount"],
        kpis_calculated=["Total Transaction Amount by KYC Status"],
    ),
    Intent(
        "aggregate_chargebacks_by_severity",
        ["compare chargebacks by severity", "severity level", "chargebacks by severity", "dispute severity distribution"],
        "SELECT severity, COUNT(*) AS count, SUM(disputed_amount) AS total_disputed FROM fact_chargebacks "
        "GROUP BY severity ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END;",
        {"type": "pie", "x_axis": "severity", "y_axis": "count", "title": "Chargebacks by Severity Level"},
        ["Show chargeback reason distribution.", "Show disputes reported after 7 days.", "Show high-risk merchants with repeated disputes."],
        "Group fact_chargebacks by severity, counting rows and summing disputed_amount, ordered Critical -> Low.",
        _s_severity,
        primary_table="fact_chargebacks",
        variables_fetched=["fact_chargebacks.severity", "fact_chargebacks.disputed_amount"],
        kpis_calculated=["Chargeback Count by Severity", "Disputed Amount by Severity"],
    ),
    Intent(
        "filter_delayed_disputes",
        ["disputes reported after 7 days", "reported after 7 days", "delayed disputes", "reporting delay"],
        "SELECT complaint_id, user_id, merchant_id, reporting_delay_days, disputed_amount, reason_code "
        "FROM fact_chargebacks WHERE reporting_delay_days > 7 ORDER BY reporting_delay_days DESC LIMIT 200;",
        {"type": "table", "x_axis": "complaint_id", "y_axis": "reporting_delay_days", "title": "Disputes Reported After 7+ Days"},
        ["What's the average dispute reporting delay?", "Show chargebacks with logically invalid timestamps.", "Show chargeback reason distribution."],
        "Filter fact_chargebacks to reporting_delay_days > 7, sorted by delay descending.",
        _s_delayed_disputes,
        primary_table="fact_chargebacks",
        variables_fetched=["fact_chargebacks.reporting_delay_days", "fact_chargebacks.disputed_amount"],
        kpis_calculated=["Disputes with Reporting Delay > 7 Days"],
    ),
    Intent(
        "rank_merchants_by_cb_ratio",
        ["highest chargeback-to-transaction ratio", "chargeback to transaction ratio", "cb to txn ratio", "highest dispute ratio"],
        "WITH txn AS (SELECT merchant_id, COUNT(*) AS txn_count FROM fact_transactions GROUP BY merchant_id), "
        "cb AS (SELECT merchant_id, COUNT(*) AS cb_count FROM fact_chargebacks GROUP BY merchant_id) "
        "SELECT m.merchant_id, m.merchant_name, COALESCE(cb.cb_count,0) AS cb_count, COALESCE(txn.txn_count,0) AS txn_count, "
        "CAST(COALESCE(cb.cb_count,0) AS REAL) / NULLIF(txn.txn_count,0) AS cb_ratio "
        "FROM dim_merchants m LEFT JOIN txn ON txn.merchant_id = m.merchant_id LEFT JOIN cb ON cb.merchant_id = m.merchant_id "
        "WHERE COALESCE(txn.txn_count,0) >= 5 AND COALESCE(cb.cb_count,0) >= 3 "
        "ORDER BY cb_ratio DESC LIMIT 10;",
        {"type": "table", "x_axis": "merchant_name", "y_axis": "cb_ratio", "title": "Highest Chargeback-to-Transaction Ratio (min. 5 txns, 3 disputes)"},
        ["Show top merchants by chargeback count.", "Which merchants have repeated disputes (high-risk)?", "Show dispute rate by merchant category."],
        "CTEs count transactions and chargebacks per merchant_id, then compute cb_count/txn_count, filtered to a minimum sample (>=5 txns, >=3 disputes) so the ratio isn't dominated by 1-2 transaction merchants.",
        _s_highest_ratio,
        primary_table="dim_merchants",
        joined_tables=["fact_transactions", "fact_chargebacks"],
        join_conditions=[
            "fact_transactions.merchant_id = dim_merchants.merchant_id",
            "fact_chargebacks.merchant_id = dim_merchants.merchant_id",
        ],
        variables_fetched=["dim_merchants.merchant_name", "fact_transactions.txn_id", "fact_chargebacks.complaint_id"],
        kpis_calculated=["Chargeback-to-Transaction Ratio by Merchant"],
    ),
    Intent(
        "rank_merchants_by_disputed_amount",
        ["top merchants by disputed amount", "merchants by disputed amount"],
        "SELECT m.merchant_id, m.merchant_name, m.merchant_category, SUM(c.disputed_amount) AS total_disputed, COUNT(*) AS cb_count "
        "FROM fact_chargebacks c JOIN dim_merchants m ON c.merchant_id = m.merchant_id "
        "GROUP BY m.merchant_id, m.merchant_name, m.merchant_category ORDER BY total_disputed DESC LIMIT 10;",
        {"type": "bar", "x_axis": "merchant_name", "y_axis": "total_disputed", "title": "Top Merchants by Disputed Amount"},
        ["Which merchant has the highest chargeback count?", "Show merchants with repeated disputes.", "Which merchant category has the highest disputed amount?"],
        "Join fact_chargebacks to dim_merchants on merchant_id, sum disputed_amount per merchant, top 10.",
        _s_top_merchants_disputed_amount,
        primary_table="fact_chargebacks",
        joined_tables=["dim_merchants"],
        join_conditions=["fact_chargebacks.merchant_id = dim_merchants.merchant_id"],
        variables_fetched=["dim_merchants.merchant_name", "dim_merchants.merchant_category", "fact_chargebacks.disputed_amount"],
        kpis_calculated=["Total Disputed Amount by Merchant"],
    ),
    Intent(
        "filter_high_risk_merchants",
        ["high-risk merchants", "high risk merchants", "merchants with repeated disputes", "repeated disputes merchants"],
        "SELECT m.merchant_id, m.merchant_name, m.merchant_category, m.merchant_status, COUNT(*) AS cb_count "
        "FROM fact_chargebacks c JOIN dim_merchants m ON c.merchant_id = m.merchant_id "
        "GROUP BY m.merchant_id, m.merchant_name, m.merchant_category, m.merchant_status "
        "HAVING COUNT(*) >= 2 ORDER BY cb_count DESC;",
        {"type": "table", "x_axis": "merchant_name", "y_axis": "cb_count", "title": "High-Risk Merchants (2+ Repeated Disputes)"},
        ["Show high-risk users with repeated disputes.", "Which merchants had sudden transaction spikes?", "Which merchant has the highest chargeback-to-transaction ratio?"],
        "Join fact_chargebacks to dim_merchants, group by merchant, HAVING COUNT(*) >= 2 to isolate repeat-dispute merchants.",
        _s_high_risk_merchants,
        primary_table="fact_chargebacks",
        joined_tables=["dim_merchants"],
        join_conditions=["fact_chargebacks.merchant_id = dim_merchants.merchant_id"],
        variables_fetched=["dim_merchants.merchant_name", "dim_merchants.merchant_status"],
        kpis_calculated=["High-Risk Merchant Count (2+ Disputes)"],
    ),
    Intent(
        "filter_high_risk_users",
        ["high-risk users", "high risk users", "users with repeated disputes", "repeat dispute users"],
        "SELECT c.user_id, cu.full_name, cu.kyc_status, COUNT(*) AS cb_count, SUM(c.disputed_amount) AS total_disputed "
        "FROM fact_chargebacks c LEFT JOIN dim_customers cu ON c.user_id = cu.user_id "
        "GROUP BY c.user_id, cu.full_name, cu.kyc_status HAVING COUNT(*) >= 2 ORDER BY cb_count DESC LIMIT 25;",
        {"type": "table", "x_axis": "user_id", "y_axis": "cb_count", "title": "High-Risk Users (2+ Repeated Disputes)"},
        ["Show top 10 users by disputed amount.", "Which of these users have no KYC record?", "Show high-risk merchants with repeated disputes."],
        "Left join fact_chargebacks to dim_customers (LEFT so unmatched users still appear), group by user, HAVING COUNT(*) >= 2.",
        _s_high_risk_users,
        primary_table="fact_chargebacks",
        joined_tables=["dim_customers"],
        join_conditions=["fact_chargebacks.user_id = dim_customers.user_id"],
        variables_fetched=["dim_customers.full_name", "dim_customers.kyc_status"],
        kpis_calculated=["High-Risk User Count (2+ Disputes)"],
    ),
    Intent(
        "filter_merchant_transaction_spikes",
        ["sudden transaction spikes", "transaction spikes", "merchants with spikes", "suspicious transaction clusters", "same-day spike"],
        "SELECT merchant_id, DATE(timestamp) AS txn_date, COUNT(*) AS txn_count FROM fact_transactions "
        "GROUP BY merchant_id, DATE(timestamp) HAVING COUNT(*) >= 2 ORDER BY txn_count DESC LIMIT 25;",
        {"type": "table", "x_axis": "txn_date", "y_axis": "txn_count", "title": "Merchant Same-Day Transaction Spikes (Suspicious Clusters)"},
        ["Did any spike merchant also get a chargeback within 10 days?", "Show high-risk merchants with repeated disputes.", "Show top merchants by chargeback count."],
        "Group fact_transactions by merchant_id + calendar date, HAVING COUNT(*) >= 2 -- anomalous against this population's ~1-txn/90-day norm.",
        _s_merchant_spikes,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.merchant_id", "fact_transactions.timestamp"],
        kpis_calculated=["Merchant Same-Day Transaction Spike Count"],
    ),
    Intent(
        "filter_missing_invalid_utr",
        ["missing utr", "invalid utr", "utr format", "transactions missing utr"],
        "SELECT txn_id, user_id, merchant_id, amount, utr, utr_valid, utr_missing, status FROM fact_transactions "
        "WHERE utr_missing = 1 OR utr_valid = 0 LIMIT 200;",
        {"type": "table", "x_axis": "txn_id", "y_axis": "amount", "title": "Transactions Missing UTR or with Invalid UTR Format"},
        ["Do missing-UTR transactions correlate with failed status?", "What's the overall failed transaction rate?", "Show daily transaction volume trend."],
        "Filter fact_transactions to utr_missing = 1 OR utr_valid = 0 (both flags precomputed by the cleaning pipeline).",
        _s_missing_invalid_utr,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.utr", "fact_transactions.utr_valid", "fact_transactions.utr_missing"],
        kpis_calculated=["Missing/Invalid UTR Transaction Count"],
    ),
    Intent(
        "aggregate_dispute_rate_by_category",
        ["dispute rate by merchant category", "chargeback rate by category", "dispute rate by category"],
        "WITH txn AS (SELECT m.merchant_category, COUNT(*) AS txn_count FROM fact_transactions t "
        "JOIN dim_merchants m ON t.merchant_id = m.merchant_id GROUP BY m.merchant_category), "
        "cb AS (SELECT m.merchant_category, COUNT(*) AS cb_count FROM fact_chargebacks c "
        "JOIN dim_merchants m ON c.merchant_id = m.merchant_id GROUP BY m.merchant_category) "
        "SELECT txn.merchant_category, COALESCE(cb.cb_count,0) AS cb_count, txn.txn_count, "
        "CAST(COALESCE(cb.cb_count,0) AS REAL) / txn.txn_count AS dispute_rate "
        "FROM txn LEFT JOIN cb ON cb.merchant_category = txn.merchant_category ORDER BY dispute_rate DESC;",
        {"type": "bar", "x_axis": "merchant_category", "y_axis": "dispute_rate", "title": "Dispute Rate by Merchant Category"},
        ["Which merchant category has the highest disputed amount?", "Which merchant has the highest chargeback-to-transaction ratio?", "Show top merchants by disputed amount."],
        "Two CTEs count transactions and chargebacks per merchant_category (both via dim_merchants), then divide to get a per-category dispute rate.",
        _s_dispute_rate_by_category,
        primary_table="dim_merchants",
        joined_tables=["fact_transactions", "fact_chargebacks"],
        join_conditions=[
            "fact_transactions.merchant_id = dim_merchants.merchant_id",
            "fact_chargebacks.merchant_id = dim_merchants.merchant_id",
        ],
        variables_fetched=["dim_merchants.merchant_category", "fact_transactions.txn_id", "fact_chargebacks.complaint_id"],
        kpis_calculated=["Dispute Rate by Merchant Category"],
    ),
    Intent(
        "aggregate_pending_rate",
        ["pending transaction rate", "pending rate"],
        "SELECT SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) AS pending_count, COUNT(*) AS total_count FROM fact_transactions;",
        {"type": "metric_card", "x_axis": None, "y_axis": "pending_count", "title": "Pending Transaction Rate"},
        ["What's the failed transaction rate?", "Show pending transactions over time.", "Show daily transaction volume trend."],
        "Count PENDING-status rows over total rows in fact_transactions.",
        _s_pending_rate,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.status"],
        kpis_calculated=["Pending Transaction Rate"],
    ),
    Intent(
        "aggregate_failed_rate",
        ["failed transaction rate", "failure rate"],
        "SELECT SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed_count, COUNT(*) AS total_count FROM fact_transactions;",
        {"type": "metric_card", "x_axis": None, "y_axis": "failed_count", "title": "Failed Transaction Rate"},
        ["What's the pending transaction rate?", "Show the failed-transaction rate by hour.", "Compare successful vs failed transactions by day."],
        "Count FAILED-status rows over total rows in fact_transactions.",
        _s_failed_rate,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.status"],
        kpis_calculated=["Failed Transaction Rate"],
    ),
    Intent(
        "aggregate_avg_txn_value",
        ["average transaction value", "avg transaction value", "average txn value"],
        "SELECT AVG(amount) AS avg_amount, COUNT(*) AS txn_count FROM fact_transactions;",
        {"type": "metric_card", "x_axis": None, "y_axis": "avg_amount", "title": "Average Transaction Value"},
        ["Show the average transaction value trend over time.", "What's the average transaction value for successful transactions only?", "Show total transaction amount by merchant category."],
        "AVG(amount) across all of fact_transactions.",
        _s_avg_txn_value,
        primary_table="fact_transactions",
        variables_fetched=["fact_transactions.amount"],
        kpis_calculated=["Average Transaction Value"],
    ),
]

_AMBIGUOUS_TRIGGER = re.compile(r"\bamount\b", re.IGNORECASE)

# Fixed confidence tiers (see module docstring for why these are rule-based,
# not a trained-model probability).
CONFIDENCE_MATCH = 0.95
CONFIDENCE_AMBIGUOUS = 0.5
CONFIDENCE_NO_MATCH = 0.0


def _score(question: str, intent: Intent) -> int:
    best = 0
    for phrase in intent.keywords:
        if phrase in question:
            best = max(best, len(phrase))
    return best


def match_intent(question: str) -> dict:
    q = question.strip().lower()
    keywords_matched = extract_table_keywords(q)

    if not q:
        return {
            "status": "no_match",
            "examples": _example_questions(),
            "keywords_matched": keywords_matched,
            "confidence_score": CONFIDENCE_NO_MATCH,
        }

    scored = sorted(((_score(q, i), i) for i in INTENTS), key=lambda t: t[0], reverse=True)
    best_score, best_intent = scored[0]

    if best_score >= 5:  # matched a real phrase, not a coincidental short substring
        return {
            "status": "ok",
            "intent": best_intent.name,
            "sql": best_intent.sql,
            "viz": best_intent.viz,
            "followups": best_intent.followups,
            "thought_process": best_intent.thought,
            "summary_fn": best_intent.summary_fn,
            "keywords_matched": keywords_matched,
            "confidence_score": CONFIDENCE_MATCH,
            "er_mapping": best_intent.er_mapping(),
        }

    # Ambiguity rule: "amount" with no template match AND no qualifier
    # telling us which table it means doesn't distinguish transaction volume
    # from disputed/chargeback volume -- these come from different tables and
    # can give very different answers, so ask rather than guess. This also
    # covers the ">90% confidence, else clarify" rule generally: anything
    # that didn't hit a real phrase match is by definition below the 0.95
    # match tier, so it never proceeds to a speculative join.
    if _AMBIGUOUS_TRIGGER.search(q):
        has_qualifier = any(w in q for w in ["transaction", "txn", "dispute", "chargeback", "disputed"])
        if not has_qualifier:
            return {
                "status": "ambiguous",
                "intent": "clarify_amount_ambiguity",
                "thought_process": "The question mentions 'amount' without specifying whether it means total transaction volume or disputed/chargeback amount -- these come from different tables (fact_transactions vs fact_chargebacks) and can give very different answers.",
                "clarification": "Do you mean total transaction amount (fact_transactions.amount) or disputed/chargeback amount (fact_chargebacks.disputed_amount)? Try rephrasing with one of those terms, e.g. 'total transaction amount by category' or 'disputed amount by category'.",
                "suggested_followups": ["Total transaction amount by merchant category", "Total disputed amount by merchant category"],
                "keywords_matched": keywords_matched,
                "confidence_score": CONFIDENCE_AMBIGUOUS,
            }

    return {
        "status": "no_match",
        "examples": _example_questions(),
        "keywords_matched": keywords_matched,
        "confidence_score": CONFIDENCE_NO_MATCH,
    }


def _example_questions():
    seen = set()
    out = []
    for i in INTENTS:
        if i.keywords[0] not in seen:
            out.append(i.keywords[0])
            seen.add(i.keywords[0])
    return out
