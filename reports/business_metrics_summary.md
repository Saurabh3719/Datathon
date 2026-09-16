# Business Metrics Summary

Computed from the cleaned star schema (`data/cleaned/`). Figures marked *(all statuses)* include success/failed/pending attempts; figures marked *(success only)* reflect money that actually moved.

## Core Transaction KPIs

- **Total transaction count:** 20,000
- **Total transaction amount (all statuses):** ₹249,772,508.82
- **Total transaction amount (success only):** ₹170,844,515.41
- **Average transaction value (all statuses):** ₹12,488.63
- **Average transaction value (success only):** ₹12,535.37
- **Success rate:** 68.14%
- **Failed transaction rate:** 7.76%
- **Pending transaction rate:** 24.09%
- **Transactions missing UTR:** 1,000 (5.00%)
- **Transactions with invalid UTR format:** 0 (0.00%)

## Daily Transaction Trend

- **Date range:** 2026-01-01 to 2026-03-31

## Merchant Category Performance

- **Top category — Unmatched / No Merchant Record:** ₹129,530,786 across 10,369 txns
- **Top category — Retail - Other:** ₹17,886,517 across 1,426 txns
- **Top category — Apparel & Fashion:** ₹13,096,776 across 1,053 txns
- **Top category — Telecom & Mobile:** ₹12,134,770 across 969 txns
- **Top category — Hotel & Lodging:** ₹11,846,407 across 952 txns

## Chargeback / Dispute KPIs

- **Chargeback count:** 2,800
- **Chargeback amount:** ₹8,001,120.80
- **Chargeback-to-transaction ratio (count):** 14.00%
- **Chargeback-to-transaction ratio (amount):** 3.20%
- **Average dispute reporting delay:** 6.5 days
- **Disputes reported after 7+ days:** 524
- **Disputes with logically impossible timestamps (excluded from delay calc):** 108

## Top Merchants by Chargeback Exposure

- **Chargebacks referencing a merchant_id with no master record (excluded from merchant leaderboards, reported as a data-quality finding):** 1,501 disputes worth ₹4,289,489
- **Merchant with most chargebacks:** Mukhopadhyay, Dua and Dada (MCH9291) — 42 disputes
- **Merchant with highest chargeback-to-transaction ratio (min 3 disputes, min 5 matched transactions):** Tak-Wali (MCH8779) — 566.7%
- **High-risk merchants (>=2 disputes, >=3 matched txns, ratio in top 10% of comparable merchants):** 6

## High-Risk Users

- **Users with 2+ disputes:** 125

## KYC Funnel

- **KYC completion rate (VERIFIED):** 64.43%
- **KYC rejection rate:** 8.15%

## Join / Data-Quality Integrity

- **Transactions with a matching KYC record:** 32.39%
- **Transactions with a matching merchant master record:** 48.16%
- **Chargebacks with a matching (valid) transaction:** 93.11%

## Suspicious Transaction Clusters (Merchant Same-Day Spikes)

- **Merchant-days with 2+ transactions (anomalous vs. the population's 1-txn/90-day norm):** 242
- **Spike merchant-days followed by a chargeback within 10 days:** 8 disputes across 4 merchants
