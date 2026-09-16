# Cleaning & Normalization Reference

This is the lookup table documentation behind `scripts/clean_pipeline.py`. Every
raw value that gets rewritten to a canonical value is listed here so the mapping
is auditable rather than a black box.

## Identifiers

`user_id`, `merchant_id`, and `txn_id` arrive in mixed formats (`USR12345`,
`usr12345`, `USR-12345`, `USR 12345`, `usr_12345`, `12345`, ...). The cleaning
rule strips every non-digit character, then re-prefixes and zero-pads to a fixed
width observed across all source files:

| Entity | Canonical prefix | Digit width | Example |
|---|---|---|---|
| Customer | `USR` | 5 | `USR16112` |
| Merchant | `MCH` | 4 | `MCH7045` |
| Transaction | `TXN` | 8 | `TXN00011869` |

A value that has zero digits after stripping cannot be recovered and the row is
excluded from the join keyspace (this only ever affected the raw
`merchant_id`/`user_id` columns; no `txn_id` row was unrecoverable).

## Transaction status (`fact_transactions.status`)

| Canonical | Raw variants seen |
|---|---|
| `SUCCESS` | `S`, `Success`, `TXN_SUCCESS`, `COMPLETED`, `SUCCESS` |
| `FAILED` | `FAILED`, `TXN_FAILED`, `Fail`, `Declined`, `F` |
| `PENDING` | `PENDING`, `Pending`, `P`, `PROCESSING`, `Initiated` |

`PROCESSING` and `Initiated` are folded into `PENDING` because both describe a
non-terminal transaction state; the distinction wasn't load-bearing for any of
the requested business metrics (failed rate, pending rate).

## KYC status (`dim_customers.kyc_status`)

| Canonical | Raw variants seen |
|---|---|
| `VERIFIED` | `Verified`, `APPROVED`, `VERIFIED`, `KYC_DONE`, `V`, `Done` |
| `PENDING` | `PENDING`, `Pending`, `P`, `IN_PROGRESS`, `Under Review` |
| `REJECTED` | `Rejected`, `R`, `REJECTED`, `Reject`, `FAILED` |

## Risk segment (`dim_customers.risk_segment`)

`low/LOW/Low` -> `LOW`, `medium/MEDIUM/Medium` -> `MEDIUM`,
`High/high/HIGH` -> `HIGH`, `UNKNOWN/unknown/Unknown` -> `UNKNOWN`.

## Merchant status (`dim_merchants.merchant_status`)

| Canonical | Raw variants seen |
|---|---|
| `ACTIVE` | `Active`, `Enabled`, `Live`, `ACTIVE`, `A` |
| `INACTIVE` | `Inactive`, `Disabled`, `INACTIVE`, `I` |
| `SUSPENDED` | `Suspended`, `SUSPENDED`, `Hold`, `S` |
| `BLOCKED` | `Blocked` |
| `CLOSED` | `Closed` |

## Business type (`dim_merchants.business_type`)

`individual` variants -> `Individual`; `partnership` variants -> `Partnership`;
`sole proprietor`/`sole-proprietor`/`sole_proprietor` -> `Sole Proprietorship`;
`private limited`/`private-limited`/`private_limited` -> `Private Limited`.

## City (`dim_customers.city`, `dim_merchants.city`)

Both files share the same alias set (abbreviations, alternate English spellings,
old names, case variants), consolidated to one spelling per city:

| Canonical | Raw variants seen |
|---|---|
| Amritsar | amritsar, ASR |
| Bengaluru | bangalore, bengaluru, BLR |
| Mumbai | bombay, mumbai, mumbay, MUMBAI |
| Kolkata | calcutta, kolkata |
| Chennai | chennai, madras |
| Delhi | delhi, dilli, new delhi, DELHI |
| Hyderabad | hyderabad, hyd, HYDERABAD |
| Jaipur | jaipur, JPR |
| Jalandhar | jalandhar, jalandar |
| Lucknow | lucknow, LKO |
| Ludhiana | ludhiana, LDH |
| Pune | pune, poona |

`state` required no cleaning — cross-checked against `city` and found internally
consistent (e.g. every Mumbai/Bombay/MUMBAI row already carried `Maharashtra`).

## MCC codes (`fact_transactions.mcc`, `dim_merchants.mcc`)

Raw MCCs appear as bare 4-digit codes, zero-padded 5-character strings (`05411`),
floats (`5411.0`), hyphenated (`MCC-5411`), or the literal strings `misc` /
`UNKNOWN`. Cleaning extracts the numeric portion and re-formats to a 4-digit
zero-padded string; `misc`/`UNKNOWN` and non-numeric values become `NULL`. In
`dim_merchants`, a null MCC is then imputed from the modal MCC code observed for
that merchant's (already-cleaned) `merchant_category`, and flagged via
`mcc_imputed`.

## Merchant category (`dim_merchants.merchant_category`)

82 raw spellings (case, underscores, abbreviations, singular/plural) were
consolidated into 10 canonical categories:

| Canonical | Raw variants folded in |
|---|---|
| Apparel & Fashion | apparel, cloths, clothing, garments, fashion |
| Books & Stationery | books, book store, books_stationery, stationery |
| Department Store | department store(s), dept_store |
| Restaurants & Food Service | food, food_services, restaurant(s), eating place |
| Grocery | grocery, groceries, grocery stores, grocery_store, kirana |
| Hotel & Lodging | hotel(s), hotel_lodging, hospitality |
| Pharmacy & Medical | medical, medical_store, pharmacy, pharmacies, chemist |
| Retail - Other | retail, retail other, misc retail, miscellaneous, other |
| Telecom & Mobile | telecom, phone service, mobile recharge |
| Transportation & Travel | transport, transportation, bus/taxi, transprt, travel |

## Amounts (`amount`, `disputed_amount`, `monthly_income`, `declared_avg_ticket_size`)

1. Strip currency markers: `₹`, `Rs.`/`Rs`, `INR` (case-insensitive).
2. Strip thousands separators (`,`).
3. `monthly_income` additionally handles a `k` suffix (×1,000) and an `l` suffix
   (×100,000, lakh).
4. Cast to float. Anything still unparseable (blank, `Not Available`, stray text)
   becomes `NULL` and is flagged (`*_missing`).
5. Negative values are **not dropped** — a negative amount/income is almost
   certainly a sign error, not a real debit-of-nothing or negative salary, so the
   value is stored as `abs(value)` and flagged `*_was_negative` for anyone who
   wants to audit or exclude them.

## Timestamps (all date/time columns)

Observed raw formats: Unix epoch seconds (`1770063471`), ISO
(`2026-01-15 00:11:30`), year-first slash (`2026/03/07`), day-first slash with
24h or 12h time (`28/02/2026 16:36:07`, `18/12/2024 08:35 AM`), day-month-name-year
(`15-Sep-2025`), and month-first dash, always paired with 12-hour time when a
time is present (`03-07-2026 09:03:11 AM`).

Parsing rule, in order:
1. A bare 9-10 digit string is treated as Unix epoch seconds.
2. A `YYYY/MM/DD...` string is parsed year-first (unambiguous).
3. Any other string containing `/` is parsed day-first (`28/02/2026` is 28 Feb,
   confirmed by cross-checking values where the first token exceeds 12).
4. Everything else (dash-separated, or a month name) is parsed month-first,
   which correctly resolves both the day-month-name case (unambiguous) and the
   pure-numeric dash case (confirmed the same way: values like `12-31-2025`
   only make sense as `MM-DD-YYYY`).

**Logical-impossibility checks**, applied after parsing (not a format issue —
these are internally-consistent dates that don't make sense *together*):
- Chargeback `reported_timestamp` earlier than `transaction_timestamp`.
- Chargeback `bank_response_timestamp` earlier than `reported_timestamp`.

Both are flagged via `timestamps_logically_valid = False`, the row is **kept**,
and `reporting_delay_days` is left null for that row rather than reporting a
negative delay.

## PAN / Aadhaar (`dim_customers`)

- PAN is cleaned to uppercase alphanumeric and validated against the standard
  `AAAAA9999A` pattern (5 letters, 4 digits, 1 letter).
- Aadhaar is cleaned to digits-only and validated as exactly 12 digits.
- Because this dataset is published to a public repository, both are **masked**
  in the output even though the data is synthetic: a valid PAN keeps its first
  2 and last 2 characters (`AB​XXXXX​XY`), a valid Aadhaar keeps only its last 4
  digits. `pan_valid`/`aadhaar_valid` booleans are retained so KYC-quality
  metrics still work without the raw ID being recoverable.

## UTR (`fact_transactions.utr`)

Digits are extracted; a UTR is valid only if exactly 10 digits remain, in which
case it's re-formatted as `UTR##########`. Anything else (missing, wrong digit
count) is flagged via `utr_valid = False`; the row is kept since a bad/missing
UTR is itself a fraud signal, not a reason to drop the transaction.

## Chargeback reason codes (`fact_chargebacks.reason_code`)

33 raw free-text/code variants were consolidated into 7 canonical fraud/dispute
categories (`reason_code_raw` preserves the original value):

| Canonical | Raw variants folded in |
|---|---|
| DUPLICATE_DEBIT | duplicate debit, DUP_DEBIT, charged twice, double debit |
| UNAUTHORIZED_TRANSACTION | Unauthorized Transaction, unauth txn, unauthorized_transaction, UNAUTHORISED, not done by me |
| ACCOUNT_TAKEOVER | Account Takeover, ATO, account hacked, login compromised |
| FRAUD_SUSPECTED | FRAUD, Fraud Suspected, fraud, scam, suspicious transaction |
| SERVICE_NOT_DELIVERED | item not received, not delivered, Merchant Not Delivered, delivery issue, Service Not Provided, service failed, merchant service issue |
| AMOUNT_MISMATCH | amount mismatch, Wrong Amount, incorrect amount, extra amount deducted |
| GENERAL_DISPUTE | customer issue, Customer Dispute, dispute raised, complaint |

## Chargeback severity, resolution status, channel

| Field | Canonical values | Mapping rule |
|---|---|---|
| `severity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` | Priority codes P1-P4 map 1:1 to Critical/High/Medium/Low; text/abbreviation variants (`H`, `High`, `HIGH`) fold into the matching level. |
| `resolution_status` | `OPEN`, `IN_PROGRESS`, `PENDING_BANK`, `RESOLVED`, `REJECTED`, `CLOSED` | Case/spacing variants (`In Progress`/`WIP`, `Pending Bank`) folded to one spelling. |
| `channel` | `IVR`, `CHATBOT`, `EMAIL`, `BRANCH`, `APP`, `CALL_CENTER` | Case-only variants folded (`ivr`/`IVR`, `chatbot`/`CHATBOT`). |

## Duplicates

| File | Dedup key | Strategy |
|---|---|---|
| `track1_upi_transactions.csv` | exact row, then canonical `txn_id` | Drop exact duplicate rows first (400 removed), then drop duplicate `txn_id` after standardization (0 additional — every remaining `txn_id` was already unique). |
| `track1_kyc_records.csv` | canonical `user_id` | Keep the row with the fewest nulls (most complete); tie-break on most recent `signup_timestamp`. |
| `track1_merchants_master.csv` | canonical `merchant_id` | Same rule: most complete, tie-break on earliest `onboarding_date`. |
| `track1_chargebacks.json` | `complaint_id` | Drop exact duplicate `complaint_id` (84 removed). |

## Foreign keys

No transaction or chargeback row is dropped for referencing an ID that doesn't
exist in the corresponding master file. Instead, `*_valid_fk` boolean columns
are added (`user_id_valid_fk`, `merchant_id_valid_fk`, `txn_id_valid_fk`) so
downstream analysis can choose to include, exclude, or specifically study the
unmatched population — which, in this dataset, turned out to be large enough
(see `reports/data_quality_report.md`) to be a headline finding rather than
noise to discard.
