"""
Computes the business/fraud/risk metrics defined in the dataset notes from the
cleaned star schema, writes reports/business_metrics_summary.md, and writes
dashboard/data.json (pre-aggregated series consumed by dashboard/index.html).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
CLEANED = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"
DASHBOARD = ROOT / "dashboard"


def load():
    customers = pd.read_csv(CLEANED / "dim_customers.csv", parse_dates=["signup_timestamp", "date_of_birth"])
    merchants = pd.read_csv(CLEANED / "dim_merchants.csv", parse_dates=["onboarding_date"])
    merchants["mcc"] = merchants["mcc"].astype("Int64").astype(str).str.zfill(4)
    txns = pd.read_csv(CLEANED / "fact_transactions.csv", parse_dates=["timestamp"])
    cbk = pd.read_csv(
        CLEANED / "fact_chargebacks.csv",
        parse_dates=["transaction_timestamp", "reported_timestamp", "bank_response_timestamp"],
    )
    return customers, merchants, txns, cbk


def to_records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def main():
    customers, merchants, txns, cbk = load()
    data = {}
    md = []

    def h(title):
        md.append(f"\n## {title}\n")

    def kv(label, value):
        md.append(f"- **{label}:** {value}")

    md.append("# Business Metrics Summary\n")
    md.append(
        "Computed from the cleaned star schema (`data/cleaned/`). Figures marked "
        "*(all statuses)* include success/failed/pending attempts; figures marked "
        "*(success only)* reflect money that actually moved."
    )

    # ---- Core transaction KPIs ------------------------------------------------
    h("Core Transaction KPIs")
    total_txn = len(txns)
    total_amount_all = txns["amount"].sum()
    success_mask = txns["status"] == "SUCCESS"
    total_amount_success = txns.loc[success_mask, "amount"].sum()
    avg_txn_value_all = txns["amount"].mean()
    avg_txn_value_success = txns.loc[success_mask, "amount"].mean()
    failed_rate = (txns["status"] == "FAILED").mean()
    pending_rate = (txns["status"] == "PENDING").mean()
    success_rate = success_mask.mean()

    kv("Total transaction count", f"{total_txn:,}")
    kv("Total transaction amount (all statuses)", f"₹{total_amount_all:,.2f}")
    kv("Total transaction amount (success only)", f"₹{total_amount_success:,.2f}")
    kv("Average transaction value (all statuses)", f"₹{avg_txn_value_all:,.2f}")
    kv("Average transaction value (success only)", f"₹{avg_txn_value_success:,.2f}")
    kv("Success rate", f"{success_rate:.2%}")
    kv("Failed transaction rate", f"{failed_rate:.2%}")
    kv("Pending transaction rate", f"{pending_rate:.2%}")

    utr_missing_rate = txns["utr_missing"].mean()
    utr_invalid_rate = ((~txns["utr_valid"]) & (~txns["utr_missing"])).mean()
    kv("Transactions missing UTR", f"{txns['utr_missing'].sum():,} ({utr_missing_rate:.2%})")
    kv("Transactions with invalid UTR format", f"{((~txns['utr_valid']) & (~txns['utr_missing'])).sum():,} ({utr_invalid_rate:.2%})")

    data["kpi"] = {
        "total_txn": int(total_txn),
        "total_amount_all": float(total_amount_all),
        "total_amount_success": float(total_amount_success),
        "avg_txn_value_all": float(avg_txn_value_all),
        "avg_txn_value_success": float(avg_txn_value_success),
        "success_rate": float(success_rate),
        "failed_rate": float(failed_rate),
        "pending_rate": float(pending_rate),
        "utr_missing_rate": float(utr_missing_rate),
        "utr_invalid_rate": float(utr_invalid_rate),
    }

    # ---- Daily trend ------------------------------------------------------
    h("Daily Transaction Trend")
    daily = txns.assign(date=txns["timestamp"].dt.date).groupby("date").agg(
        txn_count=("txn_id", "count"),
        txn_amount=("amount", "sum"),
        failed_count=("status", lambda s: (s == "FAILED").sum()),
        pending_count=("status", lambda s: (s == "PENDING").sum()),
        success_count=("status", lambda s: (s == "SUCCESS").sum()),
    ).reset_index()
    daily["date"] = daily["date"].astype(str)
    data["daily_trend"] = to_records(daily)
    kv("Date range", f"{daily['date'].min()} to {daily['date'].max()}")

    # ---- Failed transaction trend by hour ---------------------------------
    hourly_fail = txns.assign(hour=txns["timestamp"].dt.hour).groupby("hour").agg(
        txn_count=("txn_id", "count"),
        failed_count=("status", lambda s: (s == "FAILED").sum()),
    ).reset_index()
    hourly_fail["failed_rate"] = hourly_fail["failed_count"] / hourly_fail["txn_count"]
    data["hourly_failed_rate"] = to_records(hourly_fail)

    # ---- Merchant category performance ------------------------------------
    h("Merchant Category Performance")
    txn_m = txns.merge(merchants[["merchant_id", "merchant_category"]], on="merchant_id", how="left")
    txn_m["merchant_category"] = txn_m["merchant_category"].fillna("Unmatched / No Merchant Record")
    cat_perf = txn_m.groupby("merchant_category").agg(
        txn_count=("txn_id", "count"),
        txn_amount=("amount", "sum"),
        failed_count=("status", lambda s: (s == "FAILED").sum()),
    ).reset_index()
    cat_perf["failed_rate"] = cat_perf["failed_count"] / cat_perf["txn_count"]
    cat_perf = cat_perf.sort_values("txn_amount", ascending=False)
    data["category_performance"] = to_records(cat_perf)
    for _, row in cat_perf.head(5).iterrows():
        kv(f"Top category — {row['merchant_category']}", f"₹{row['txn_amount']:,.0f} across {row['txn_count']:,} txns")

    # ---- Chargeback core KPIs ----------------------------------------------
    h("Chargeback / Dispute KPIs")
    cb_count = len(cbk)
    cb_amount = cbk["disputed_amount"].sum()
    cb_to_txn_ratio = cb_count / total_txn
    cb_to_txn_amount_ratio = cb_amount / total_amount_all if total_amount_all else np.nan
    avg_delay = cbk.loc[cbk["timestamps_logically_valid"], "reporting_delay_days"].mean()

    kv("Chargeback count", f"{cb_count:,}")
    kv("Chargeback amount", f"₹{cb_amount:,.2f}")
    kv("Chargeback-to-transaction ratio (count)", f"{cb_to_txn_ratio:.2%}")
    kv("Chargeback-to-transaction ratio (amount)", f"{cb_to_txn_amount_ratio:.2%}")
    kv("Average dispute reporting delay", f"{avg_delay:.1f} days")
    kv("Disputes reported after 7+ days", f"{(cbk['reporting_delay_days'] > 7).sum():,}")
    kv("Disputes with logically impossible timestamps (excluded from delay calc)", f"{(~cbk['timestamps_logically_valid']).sum():,}")

    data["kpi"].update({
        "cb_count": int(cb_count),
        "cb_amount": float(cb_amount),
        "cb_to_txn_ratio": float(cb_to_txn_ratio),
        "cb_to_txn_amount_ratio": float(cb_to_txn_amount_ratio),
        "avg_delay_days": None if pd.isna(avg_delay) else float(avg_delay),
        "delayed_7d_count": int((cbk["reporting_delay_days"] > 7).sum()),
    })

    # ---- Chargeback-to-transaction ratio by merchant category -------------
    cb_m = cbk.merge(merchants[["merchant_id", "merchant_category"]], on="merchant_id", how="left")
    cb_m["merchant_category"] = cb_m["merchant_category"].fillna("Unmatched / No Merchant Record")
    cb_cat = cb_m.groupby("merchant_category").agg(cb_count=("complaint_id", "count"), cb_amount=("disputed_amount", "sum")).reset_index()
    cat_ratio = cat_perf[["merchant_category", "txn_count", "txn_amount"]].merge(cb_cat, on="merchant_category", how="outer").fillna(0)
    cat_ratio["cb_to_txn_ratio"] = cat_ratio.apply(lambda r: (r["cb_count"] / r["txn_count"]) if r["txn_count"] else 0, axis=1)
    cat_ratio = cat_ratio.sort_values("cb_to_txn_ratio", ascending=False)
    data["category_dispute_ratio"] = to_records(cat_ratio)

    # ---- Reason / severity / resolution distributions ----------------------
    data["reason_distribution"] = to_records(cbk["reason_code"].value_counts().rename_axis("reason_code").reset_index(name="count"))
    data["severity_distribution"] = to_records(cbk["severity"].value_counts().rename_axis("severity").reset_index(name="count"))
    data["resolution_distribution"] = to_records(cbk["resolution_status"].value_counts().rename_axis("resolution_status").reset_index(name="count"))
    data["channel_distribution"] = to_records(cbk["channel"].value_counts().rename_axis("channel").reset_index(name="count"))

    # ---- Top merchants by chargeback count / amount ------------------------
    # Ranked only among merchants with a real master-data record; chargebacks/transactions
    # that reference a merchant_id absent from the master file are reported separately below
    # as a data-quality/"unidentified merchant" finding rather than mixed into the leaderboard.
    h("Top Merchants by Chargeback Exposure")
    valid_cbk = cbk[cbk["merchant_id_valid_fk"]]
    valid_txn = txns[txns["merchant_id_valid_fk"]]
    m_cb = valid_cbk.groupby("merchant_id").agg(cb_count=("complaint_id", "count"), cb_amount=("disputed_amount", "sum")).reset_index()
    m_txn = valid_txn.groupby("merchant_id").agg(txn_count=("txn_id", "count"), txn_amount=("amount", "sum")).reset_index()
    m_full = merchants[["merchant_id", "merchant_name", "merchant_category", "merchant_status"]].merge(
        m_cb, on="merchant_id", how="left"
    ).merge(m_txn, on="merchant_id", how="left")
    m_full[["cb_count", "cb_amount", "txn_count", "txn_amount"]] = m_full[["cb_count", "cb_amount", "txn_count", "txn_amount"]].fillna(0)
    m_full["cb_to_txn_ratio"] = m_full.apply(lambda r: (r["cb_count"] / r["txn_count"]) if r["txn_count"] else np.nan, axis=1)

    top_by_count = m_full[m_full["cb_count"] > 0].sort_values("cb_count", ascending=False).head(15)
    top_by_amount = m_full[m_full["cb_amount"] > 0].sort_values("cb_amount", ascending=False).head(15)
    # require a minimum matched-transaction sample so the ratio isn't dominated by 1-2 txn merchants
    top_by_ratio = m_full[(m_full["cb_count"] >= 3) & (m_full["txn_count"] >= 5)].sort_values("cb_to_txn_ratio", ascending=False).head(15)
    data["top_merchants_by_cb_count"] = to_records(top_by_count)
    data["top_merchants_by_cb_amount"] = to_records(top_by_amount)
    data["top_merchants_by_cb_ratio"] = to_records(top_by_ratio)

    unmatched_cb_count = (~cbk["merchant_id_valid_fk"]).sum()
    unmatched_cb_amount = cbk.loc[~cbk["merchant_id_valid_fk"], "disputed_amount"].sum()
    kv(
        "Chargebacks referencing a merchant_id with no master record (excluded from merchant leaderboards, reported as a data-quality finding)",
        f"{unmatched_cb_count:,} disputes worth ₹{unmatched_cb_amount:,.0f}",
    )
    data["kpi"]["unmatched_merchant_cb_count"] = int(unmatched_cb_count)
    data["kpi"]["unmatched_merchant_cb_amount"] = float(unmatched_cb_amount)

    kv("Merchant with most chargebacks", f"{top_by_count.iloc[0]['merchant_name']} ({top_by_count.iloc[0]['merchant_id']}) — {int(top_by_count.iloc[0]['cb_count'])} disputes")
    if len(top_by_ratio):
        kv(
            "Merchant with highest chargeback-to-transaction ratio (min 3 disputes, min 5 matched transactions)",
            f"{top_by_ratio.iloc[0]['merchant_name']} ({top_by_ratio.iloc[0]['merchant_id']}) — {top_by_ratio.iloc[0]['cb_to_txn_ratio']:.1%}",
        )

    # High-risk merchants: top decile by ratio among merchants with enough sample to be meaningful,
    # union'd with any merchant already Suspended/Blocked in the master file.
    sample_pool = m_full[(m_full["cb_count"] >= 2) & (m_full["txn_count"] >= 3)]
    threshold_ratio = sample_pool["cb_to_txn_ratio"].quantile(0.90) if len(sample_pool) else np.inf
    high_risk_merchants = sample_pool[sample_pool["cb_to_txn_ratio"] >= threshold_ratio]
    data["high_risk_merchants"] = to_records(high_risk_merchants.sort_values("cb_to_txn_ratio", ascending=False))
    kv("High-risk merchants (>=2 disputes, >=3 matched txns, ratio in top 10% of comparable merchants)", f"{len(high_risk_merchants):,}")

    # ---- High-risk users ----------------------------------------------------
    h("High-Risk Users")
    u_cb = cbk.groupby("user_id").agg(cb_count=("complaint_id", "count"), cb_amount=("disputed_amount", "sum")).reset_index()
    u_full = u_cb.merge(customers[["user_id", "full_name", "kyc_status", "risk_segment"]], on="user_id", how="left")
    repeat_users = u_full[u_full["cb_count"] >= 2].sort_values(["cb_count", "cb_amount"], ascending=False)
    data["high_risk_users"] = to_records(repeat_users.head(25))
    kv("Users with 2+ disputes", f"{len(repeat_users):,}")

    high_value_cb = cbk.sort_values("disputed_amount", ascending=False).head(20)
    high_value_cb = high_value_cb.merge(customers[["user_id", "full_name"]], on="user_id", how="left")
    data["high_value_chargebacks"] = to_records(high_value_cb)

    # ---- KYC funnel -----------------------------------------------------
    h("KYC Funnel")
    kyc_dist = customers["kyc_status"].value_counts()
    kyc_completion_rate = kyc_dist.get("VERIFIED", 0) / len(customers)
    kyc_rejection_rate = kyc_dist.get("REJECTED", 0) / len(customers)
    kv("KYC completion rate (VERIFIED)", f"{kyc_completion_rate:.2%}")
    kv("KYC rejection rate", f"{kyc_rejection_rate:.2%}")
    data["kyc_distribution"] = to_records(kyc_dist.rename_axis("kyc_status").reset_index(name="count"))
    risk_dist = customers["risk_segment"].fillna("Not Provided").value_counts()
    data["risk_segment_distribution"] = to_records(risk_dist.rename_axis("risk_segment").reset_index(name="count"))
    data["kpi"]["kyc_completion_rate"] = float(kyc_completion_rate)
    data["kpi"]["kyc_rejection_rate"] = float(kyc_rejection_rate)

    # Dispute rate for non-verified KYC users vs verified
    txn_c = txns.merge(customers[["user_id", "kyc_status"]], on="user_id", how="left")
    cb_c = cbk.merge(customers[["user_id", "kyc_status"]], on="user_id", how="left")
    kyc_risk = txn_c.groupby(txn_c["kyc_status"].fillna("NO_KYC_RECORD")).agg(txn_count=("txn_id", "count")).reset_index()
    kyc_risk_cb = cb_c.groupby(cb_c["kyc_status"].fillna("NO_KYC_RECORD")).agg(cb_count=("complaint_id", "count")).reset_index()
    kyc_risk = kyc_risk.merge(kyc_risk_cb, on="kyc_status", how="left").fillna(0)
    kyc_risk["cb_rate"] = kyc_risk["cb_count"] / kyc_risk["txn_count"]
    data["dispute_rate_by_kyc_status"] = to_records(kyc_risk)

    # ---- Data quality / join integrity --------------------------------------
    h("Join / Data-Quality Integrity")
    user_fk_valid_rate = txns["user_id_valid_fk"].mean()
    merchant_fk_valid_rate = txns["merchant_id_valid_fk"].mean()
    kv("Transactions with a matching KYC record", f"{user_fk_valid_rate:.2%}")
    kv("Transactions with a matching merchant master record", f"{merchant_fk_valid_rate:.2%}")
    kv("Chargebacks with a matching (valid) transaction", f"{cbk['txn_id_valid_fk'].mean():.2%}")
    data["kpi"]["user_fk_valid_rate"] = float(user_fk_valid_rate)
    data["kpi"]["merchant_fk_valid_rate"] = float(merchant_fk_valid_rate)
    data["kpi"]["txn_fk_valid_rate_cb"] = float(cbk["txn_id_valid_fk"].mean())

    # ---- Suspicious transaction clusters (merchant same-day spikes) ---------
    # A typical merchant in this dataset sees ~2-3 transactions across the entire 90-day
    # window (median 2, max 10), so a classic rolling z-score is meaningless here - almost
    # every merchant-day is either 0 or 1. Instead we flag same-day multi-transaction
    # clusters, which are themselves rare (~3% of active merchants) and therefore anomalous
    # relative to this population's normal one-transaction-per-visit pattern.
    h("Suspicious Transaction Clusters (Merchant Same-Day Spikes)")
    daily_m = txns.assign(date=txns["timestamp"].dt.date).groupby(["merchant_id", "date"]).size().reset_index(name="txn_count")
    spikes = daily_m[daily_m["txn_count"] >= 2].sort_values("txn_count", ascending=False)
    spikes = spikes.merge(merchants[["merchant_id", "merchant_name", "merchant_category"]], on="merchant_id", how="left")
    spikes["date"] = spikes["date"].astype(str)
    data["merchant_spikes"] = to_records(spikes.head(25))
    kv("Merchant-days with 2+ transactions (anomalous vs. the population's 1-txn/90-day norm)", f"{len(spikes):,}")

    # Spike-then-dispute correlation: merchant had a spike day, then a chargeback was filed
    # against that merchant within 10 days of it.
    spike_dates = spikes.assign(date=pd.to_datetime(spikes["date"]))[["merchant_id", "date"]]
    cb_dates = cbk.dropna(subset=["transaction_timestamp"])[["merchant_id", "transaction_timestamp", "complaint_id"]]
    merged = spike_dates.merge(cb_dates, on="merchant_id", how="inner")
    merged["gap_days"] = (merged["transaction_timestamp"] - merged["date"]).dt.days
    spike_then_dispute = merged[(merged["gap_days"] >= 0) & (merged["gap_days"] <= 10)]
    kv(
        "Spike merchant-days followed by a chargeback within 10 days",
        f"{spike_then_dispute['complaint_id'].nunique():,} disputes across {spike_then_dispute['merchant_id'].nunique():,} merchants",
    )
    data["kpi"]["spike_then_dispute_count"] = int(spike_then_dispute["complaint_id"].nunique())

    (REPORTS / "business_metrics_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (DASHBOARD / "data.json").write_text(json.dumps(data, indent=None, default=str), encoding="utf-8")
    print("\n".join(md))
    print(f"\nWrote reports/business_metrics_summary.md and dashboard/data.json")


if __name__ == "__main__":
    main()
