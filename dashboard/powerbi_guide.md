# Power BI Build Guide

This environment has no Windows/Power BI Desktop available, so the dashboard
delivered with this repo is a self-contained HTML page
(`dashboard/index.html`) built directly on top of the same cleaned tables. This
guide is what to import if you want to rebuild it natively in Power BI Desktop.

## 1. Get data

Import the four cleaned CSVs from `data/cleaned/` as-is — no Power Query
transforms are needed, cleaning already happened in `scripts/clean_pipeline.py`:

- `dim_customers.csv`
- `dim_merchants.csv`
- `fact_transactions.csv`
- `fact_chargebacks.csv`

Set column types on import:
- `*_id` columns -> Text (never Whole Number — leading structure matters, and
  they're join keys, not measures).
- `timestamp`, `signup_timestamp`, `onboarding_date`, `date_of_birth`,
  `transaction_timestamp`, `reported_timestamp`, `bank_response_timestamp` ->
  Date/Time.
- `*_valid`, `*_valid_fk`, `*_was_negative`, `*_missing`,
  `timestamps_logically_valid` -> True/False.

## 2. Model relationships (star schema)

```
dim_customers[user_id]  1 ──< fact_transactions[user_id]
dim_merchants[merchant_id] 1 ──< fact_transactions[merchant_id]
fact_transactions[txn_id]  1 ──< fact_chargebacks[txn_id]
dim_customers[user_id]  1 ──< fact_chargebacks[user_id]
dim_merchants[merchant_id] 1 ──< fact_chargebacks[merchant_id]
```

Set every relationship to **single-direction** filtering (dim -> fact), status
"Active". Because a meaningful share of `fact_transactions` and
`fact_chargebacks` rows reference an id absent from the dimension tables (see
`reports/data_quality_report.md`), these relationships will legitimately show
"some rows don't match" in Power BI's relationship view — that's expected, not
a modeling error. Do **not** switch to full outer / bidirectional filtering to
force a match; instead build the unmatched-rate measures below so the gap is
visible rather than silently dropped from visuals.

Add a **Date table** (Modeling -> New Table):
```
DateTable = CALENDAR(DATE(2023,1,1), DATE(2026,12,31))
```
Mark it as a date table (Table tools -> Mark as Date Table), and relate
`DateTable[Date]` to `fact_transactions[timestamp]` (by date part) so time
intelligence functions work.

## 3. Core measures (DAX)

```dax
Total Transactions        = COUNTROWS(fact_transactions)
Total Txn Amount          = SUM(fact_transactions[amount])
Total Txn Amount (Success)= CALCULATE([Total Txn Amount], fact_transactions[status] = "SUCCESS")
Avg Txn Value             = AVERAGE(fact_transactions[amount])

Failed Rate  = DIVIDE(CALCULATE([Total Transactions], fact_transactions[status]="FAILED"), [Total Transactions])
Pending Rate = DIVIDE(CALCULATE([Total Transactions], fact_transactions[status]="PENDING"), [Total Transactions])
Success Rate = DIVIDE(CALCULATE([Total Transactions], fact_transactions[status]="SUCCESS"), [Total Transactions])

Chargeback Count  = COUNTROWS(fact_chargebacks)
Chargeback Amount = SUM(fact_chargebacks[disputed_amount])

CB to Txn Ratio (Count)  = DIVIDE([Chargeback Count], [Total Transactions])
CB to Txn Ratio (Amount) = DIVIDE([Chargeback Amount], [Total Txn Amount])

Avg Dispute Delay (Days) =
    CALCULATE(
        AVERAGE(fact_chargebacks[reporting_delay_days]),
        fact_chargebacks[timestamps_logically_valid] = TRUE
    )

Disputes Reported After 7d =
    CALCULATE(COUNTROWS(fact_chargebacks), fact_chargebacks[reporting_delay_days] > 7)

KYC Completion Rate =
    DIVIDE(CALCULATE(COUNTROWS(dim_customers), dim_customers[kyc_status]="VERIFIED"), COUNTROWS(dim_customers))
KYC Rejection Rate =
    DIVIDE(CALCULATE(COUNTROWS(dim_customers), dim_customers[kyc_status]="REJECTED"), COUNTROWS(dim_customers))

-- Data-quality / join-integrity measures (report these alongside the KPIs above,
-- not just in a footnote — see README "Headline finding")
Txn User FK Match Rate =
    DIVIDE(CALCULATE([Total Transactions], fact_transactions[user_id_valid_fk]=TRUE), [Total Transactions])
Txn Merchant FK Match Rate =
    DIVIDE(CALCULATE([Total Transactions], fact_transactions[merchant_id_valid_fk]=TRUE), [Total Transactions])
CB Txn FK Match Rate =
    DIVIDE(CALCULATE([Chargeback Count], fact_chargebacks[txn_id_valid_fk]=TRUE), [Chargeback Count])

Merchant CB to Txn Ratio =
    VAR CB  = CALCULATE([Chargeback Count], fact_chargebacks[merchant_id_valid_fk]=TRUE)
    VAR TXN = CALCULATE([Total Transactions], fact_transactions[merchant_id_valid_fk]=TRUE)
    RETURN DIVIDE(CB, TXN)
```

## 4. Suggested pages / visuals

1. **Overview** — KPI cards (measures above), daily transaction count + amount
   line charts (as two visuals, not a dual-axis combo — see note below), a
   failed-rate-by-hour column chart.
2. **Merchant Risk** — bar chart of `Total Txn Amount` by
   `dim_merchants[merchant_category]`; bar chart of `Merchant CB to Txn Ratio`
   by category; table of top merchants by `Chargeback Count` /
   `Chargeback Amount`, filtered to `merchant_id_valid_fk = TRUE` so the
   leaderboard isn't dominated by unmatched IDs (surface those separately as a
   callout card instead).
3. **Dispute Analysis** — donut/bar of `reason_code`, `severity`,
   `resolution_status`, `channel` distributions; `Avg Dispute Delay` card;
   table of disputes with `reporting_delay_days > 7`.
4. **Customer Risk** — `kyc_status` and `risk_segment` donuts; table of users
   with `Chargeback Count` (via a measure grouped by `user_id`) >= 2.
5. **Data Quality** — the FK-match-rate measures as cards, plus a card for
   `Chargebacks on unmatched merchants` (`CALCULATE([Chargeback Count],
   fact_chargebacks[merchant_id_valid_fk] = FALSE)`). Put this page early in
   the deck, not last — the low match rate changes how every other page should
   be read.

**Avoid dual-axis combo charts** (e.g. count + amount on one chart with two
y-axes) — they're easy to misread at a glance. Prefer two small-multiple
charts side by side, which is how `dashboard/index.html` does it.

## 5. Row-level security / masking note

`dim_customers.pan_masked` and `dim_customers.aadhaar_masked` are already
masked in the CSV (synthetic data, but masked anyway since this repo is
public — see `reports/cleaning_mapping_reference.md`). Don't try to "unmask"
them from `pan_valid`/`aadhaar_valid` — those are validity flags, not a key to
the original value.
