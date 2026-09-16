"""
End-to-end cleaning pipeline for the Track 1 FinTech / BFSI UPI fraud & merchant
analytics dataset. Reads the four raw source files, standardizes every messy
field described in track1_dataset_notes.txt, resolves duplicates, validates
foreign keys, and writes an analytics-ready star schema (dim_customers,
dim_merchants, fact_transactions, fact_chargebacks) plus a data-quality report.

Usage:
    python scripts/clean_pipeline.py
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"
OUT.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

NULL_TOKENS = {
    "", "na", "n/a", "nan", "none", "null", "not available", "invalid", "-",
    "unknown", "unk",
}

report_lines = []


def log(section, text=""):
    report_lines.append(f"## {section}" if text == "" else text)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def is_null_token(v):
    if pd.isna(v):
        return True
    return str(v).strip().lower() in NULL_TOKENS


def strip_strings(df):
    """Trim leading/trailing whitespace on every string cell, right after read.

    Checks pandas.api.types.is_string_dtype rather than `dtype == object`:
    pandas 3.x infers a dedicated string dtype for text columns by default,
    which is NOT equal to `object`, so the naive check silently skips every
    column and does nothing.
    """
    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    return df


def scrub_null_tokens(df, skip=()):
    """Replace any cell that is a bare null-token placeholder (e.g. 'Unknown',
    'N/A') with real nulls, across every string column. Only exact whole-cell
    matches are replaced, so free text that merely *contains* one of these
    words (e.g. a complaint mentioning "unknown merchant") is left untouched.
    See strip_strings for why is_string_dtype is used instead of `== object`."""
    for col in df.columns:
        if col in skip or not pd.api.types.is_string_dtype(df[col]):
            continue
        df[col] = df[col].map(lambda v: None if isinstance(v, str) and is_null_token(v) else v)
    return df


def clean_id(value, prefix, width):
    if is_null_token(value):
        return None
    digits = re.sub(r"\D", "", str(value))
    if digits == "":
        return None
    return f"{prefix}{int(digits):0{width}d}"


CURRENCY_RE = re.compile(r"(₹|Rs\.?|INR)", re.IGNORECASE)


def clean_amount(value):
    if is_null_token(value):
        return np.nan
    s = CURRENCY_RE.sub("", str(value)).strip().replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


def clean_income(value):
    if is_null_token(value):
        return np.nan
    s = CURRENCY_RE.sub("", str(value)).strip()
    multiplier = 1
    if re.search(r"[kK]$", s):
        multiplier = 1_000
        s = s[:-1]
    elif re.search(r"[lL]$", s):
        multiplier = 100_000
        s = s[:-1]
    s = s.replace(",", "").strip()
    try:
        return float(s) * multiplier
    except ValueError:
        return np.nan


EPOCH_RE = re.compile(r"^\d{9,10}$")
YMD_SLASH_RE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}")


def parse_timestamp(value):
    if is_null_token(value):
        return pd.NaT
    s = str(value).strip()
    if EPOCH_RE.match(s):
        try:
            return pd.to_datetime(int(s), unit="s")
        except (ValueError, OverflowError):
            return pd.NaT
    if YMD_SLASH_RE.match(s):
        return pd.to_datetime(s, dayfirst=False, errors="coerce")
    dayfirst = "/" in s
    return pd.to_datetime(s, dayfirst=dayfirst, errors="coerce")


def normalize_category(value, mapping, default="OTHER"):
    if is_null_token(value):
        return default
    key = re.sub(r"[\s_/-]+", " ", str(value).strip().lower())
    return mapping.get(key, default)


def build_lookup(groups):
    """groups: dict of canonical_label -> list of raw variants (already lowercased/space-normalized)."""
    lookup = {}
    for canonical, variants in groups.items():
        for v in variants:
            lookup[v] = canonical
    return lookup


# ---------------------------------------------------------------------------
# Status / category normalization tables
# ---------------------------------------------------------------------------

TXN_STATUS_MAP = build_lookup({
    "SUCCESS": ["s", "success", "txn_success", "completed"],
    "FAILED": ["failed", "txn_failed", "fail", "declined", "f"],
    "PENDING": ["pending", "p", "processing", "initiated"],
})

KYC_STATUS_MAP = build_lookup({
    "VERIFIED": ["verified", "approved", "kyc_done", "v", "done"],
    "PENDING": ["pending", "p", "in_progress", "under review"],
    "REJECTED": ["rejected", "r", "reject", "failed"],
})

RISK_SEGMENT_MAP = build_lookup({
    "LOW": ["low"],
    "MEDIUM": ["medium"],
    "HIGH": ["high"],
})

MERCHANT_STATUS_MAP = build_lookup({
    "ACTIVE": ["active", "enabled", "live", "a"],
    "INACTIVE": ["inactive", "disabled", "i"],
    "SUSPENDED": ["suspended", "hold", "s"],
    "BLOCKED": ["blocked"],
    "CLOSED": ["closed"],
})

BUSINESS_TYPE_MAP = build_lookup({
    "Individual": ["individual"],
    "Partnership": ["partnership"],
    "Sole Proprietorship": ["sole proprietor", "sole-proprietor", "sole_proprietor"],
    "Private Limited": ["private limited", "private-limited", "private_limited"],
})

CITY_MAP = build_lookup({
    "Amritsar": ["amritsar", "asr"],
    "Bengaluru": ["bangalore", "bengaluru", "blr"],
    "Mumbai": ["bombay", "mumbai", "mumbay"],
    "Kolkata": ["calcutta", "kolkata"],
    "Chennai": ["chennai", "madras"],
    "Delhi": ["delhi", "dilli", "new delhi"],
    "Hyderabad": ["hyderabad", "hyd"],
    "Jaipur": ["jaipur", "jpr"],
    "Jalandhar": ["jalandhar", "jalandar"],
    "Lucknow": ["lucknow", "lko"],
    "Ludhiana": ["ludhiana", "ldh"],
    "Pune": ["pune", "poona"],
})

MERCHANT_CATEGORY_MAP = build_lookup({
    "Apparel & Fashion": ["apparel", "cloths", "clothing", "garments", "fashion"],
    "Books & Stationery": ["books", "book store", "books stationery", "stationery"],
    "Department Store": ["department store", "department stores", "dept store"],
    "Restaurants & Food Service": ["food", "food services", "restaurant", "restaurants", "eating place"],
    "Grocery": ["grocery", "groceries", "grocery stores", "grocery store", "kirana"],
    "Hotel & Lodging": ["hotel", "hotels", "hotel lodging", "hospitality"],
    "Pharmacy & Medical": ["medical", "medical store", "pharmacy", "pharmacies", "chemist"],
    "Retail - Other": ["retail", "retail other", "misc retail", "miscellaneous", "other"],
    "Telecom & Mobile": ["telecom", "phone service", "mobile recharge"],
    "Transportation & Travel": ["transport", "transportation", "bus/taxi", "transprt", "travel"],
})

RESOLUTION_STATUS_MAP = build_lookup({
    "OPEN": ["open"],
    "IN_PROGRESS": ["in progress", "wip"],
    "PENDING_BANK": ["pending bank"],
    "RESOLVED": ["resolved"],
    "REJECTED": ["rejected"],
    "CLOSED": ["closed"],
})

SEVERITY_MAP = build_lookup({
    "CRITICAL": ["p1", "crit", "critical"],
    "HIGH": ["p2", "h", "high"],
    "MEDIUM": ["p3", "m", "medium"],
    "LOW": ["p4", "l", "low"],
})

CHANNEL_MAP = build_lookup({
    "IVR": ["ivr"],
    "CHATBOT": ["chatbot"],
    "EMAIL": ["email"],
    "BRANCH": ["branch"],
    "APP": ["app"],
    "CALL_CENTER": ["call center"],
})

REASON_CODE_MAP = build_lookup({
    "DUPLICATE_DEBIT": ["duplicate debit", "dup_debit", "charged twice", "double debit"],
    "UNAUTHORIZED_TRANSACTION": [
        "unauthorized transaction", "unauth txn", "unauthorized_transaction",
        "unauthorised", "not done by me",
    ],
    "ACCOUNT_TAKEOVER": ["account takeover", "ato", "account hacked", "login compromised"],
    "FRAUD_SUSPECTED": ["fraud", "fraud suspected", "scam", "suspicious transaction"],
    "SERVICE_NOT_DELIVERED": [
        "item not received", "not delivered", "merchant not delivered",
        "delivery issue", "service not provided", "service failed",
        "merchant service issue",
    ],
    "AMOUNT_MISMATCH": ["amount mismatch", "wrong amount", "incorrect amount", "extra amount deducted"],
    "GENERAL_DISPUTE": ["customer issue", "customer dispute", "dispute raised", "complaint"],
})

MCC_CODE_RE = re.compile(r"\d+")


def clean_mcc(value):
    if is_null_token(value):
        return None
    s = str(value).strip()
    if s.lower() in ("misc", "unknown"):
        return None
    m = MCC_CODE_RE.search(s)
    if not m:
        return None
    return f"{int(m.group()):04d}"


PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def clean_pan(value):
    if is_null_token(value):
        return None, False
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    return cleaned, bool(PAN_RE.match(cleaned))


def clean_aadhaar(value):
    if is_null_token(value):
        return None, False
    digits = re.sub(r"\D", "", str(value))
    return digits, len(digits) == 12


def mask_pan(pan):
    """Always returns exactly 10 characters (real PAN length), masking the
    middle 6 and keeping only the first/last 2 visible - whether or not the
    source value was a validly-formatted PAN (see pan_valid for that)."""
    if pd.isna(pan) or pan == "":
        return None
    padded = (pan + "X" * 10)[:10]
    return padded[:2] + "X" * 6 + padded[-2:]


def mask_aadhaar(aadhaar):
    """Always returns exactly 12 characters (real Aadhaar length), masking
    all but the last 4 digits - whether or not the source value had exactly
    12 digits (see aadhaar_valid for that)."""
    if pd.isna(aadhaar) or aadhaar == "":
        return None
    padded = (aadhaar + "X" * 12)[:12]
    return "XXXXXXXX" + padded[-4:]


UTR_RE = re.compile(r"^UTR\d{10}$")


def clean_utr(value):
    if is_null_token(value):
        return None, False
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 10:
        return str(value).strip(), False
    candidate = f"UTR{digits}"
    return candidate, bool(UTR_RE.match(candidate))


# ---------------------------------------------------------------------------
# 1. KYC / customers
# ---------------------------------------------------------------------------

def clean_kyc():
    df = pd.read_csv(RAW / "track1_kyc_records.csv", dtype=str)
    df = strip_strings(df)
    n_raw = len(df)

    df["user_id"] = df["user_id"].map(lambda v: clean_id(v, "USR", 5))
    df = df[df["user_id"].notna()].copy()

    pan_clean = df["pan"].map(clean_pan)
    df["pan_clean"], df["pan_valid"] = zip(*pan_clean)
    df["pan_masked"] = [mask_pan(p) for p in df["pan_clean"]]

    aad_clean = df["aadhaar"].map(clean_aadhaar)
    df["aadhaar_clean"], df["aadhaar_valid"] = zip(*aad_clean)
    df["aadhaar_masked"] = [mask_aadhaar(a) for a in df["aadhaar_clean"]]

    df["date_of_birth"] = df["date_of_birth"].map(parse_timestamp).dt.date
    df["signup_timestamp"] = df["signup_timestamp"].map(parse_timestamp)

    df["city"] = df["city"].map(lambda v: normalize_category(v, CITY_MAP, default=None))
    df["state"] = df["state"].where(~df["state"].map(is_null_token), None)
    df["occupation"] = df["occupation"].where(~df["occupation"].map(is_null_token), None)

    income = df["monthly_income"].map(clean_income)
    income_was_negative = income < 0
    df["monthly_income"] = income.abs().round(2)
    df["income_was_negative"] = income_was_negative.fillna(False)
    df["income_missing"] = df["monthly_income"].isna()

    df["kyc_status"] = df["kyc_status"].map(lambda v: normalize_category(v, KYC_STATUS_MAP, default="PENDING"))
    df["risk_segment"] = df["risk_segment"].map(lambda v: normalize_category(v, RISK_SEGMENT_MAP, default=None))
    df["risk_segment_missing"] = df["risk_segment"].isna()

    n_before_dedup = len(df)
    df["completeness"] = df.notna().sum(axis=1)
    df = df.sort_values(["completeness", "signup_timestamp"], ascending=[False, False])
    df = df.drop_duplicates(subset="user_id", keep="first")
    n_after_dedup = len(df)

    df = scrub_null_tokens(df)

    cols = [
        "user_id", "full_name", "pan_masked", "pan_valid", "aadhaar_masked", "aadhaar_valid",
        "date_of_birth", "city", "state", "monthly_income", "income_was_negative", "income_missing",
        "occupation", "signup_timestamp", "kyc_status", "risk_segment", "risk_segment_missing",
    ]
    df = df[cols].reset_index(drop=True)

    log("Customers (KYC) cleaning", (
        f"- Raw rows: {n_raw}\n"
        f"- Rows dropped for unrecoverable user_id: {n_raw - n_before_dedup}\n"
        f"- Duplicate user_id rows collapsed (kept most complete/most recent): {n_before_dedup - n_after_dedup}\n"
        f"- Final unique customers: {n_after_dedup}\n"
        f"- PAN invalid/unparseable: {(~df['pan_valid']).sum()}\n"
        f"- Aadhaar invalid/unparseable: {(~df['aadhaar_valid']).sum()}\n"
        f"- Monthly income missing after cleaning: {df['income_missing'].sum()}\n"
        f"- Monthly income values that were negative (sign corrected): {df['income_was_negative'].sum()}\n"
        f"- Risk segment missing/literally \"Unknown\" in source (nulled, flagged - no longer stored as a fake 'UNKNOWN' category): {df['risk_segment_missing'].sum()}\n"
        f"- PAN/Aadhaar are masked in the published output (last characters only) since a public repo should not carry full ID numbers, even synthetic ones. Masked values are fixed-width: pan_masked is always exactly 10 characters, aadhaar_masked always exactly 12, matching real PAN/Aadhaar lengths regardless of source data quality.\n"
        f"- Literal placeholder text (\"Unknown\", \"N/A\", etc.) appearing as a whole-cell value in any text column is nulled rather than kept as a fake category.\n"
    ))
    return df


# ---------------------------------------------------------------------------
# 2. Merchant master
# ---------------------------------------------------------------------------

def clean_merchants():
    df = pd.read_csv(RAW / "track1_merchants_master.csv", dtype=str)
    df = strip_strings(df)
    n_raw = len(df)

    df["merchant_id"] = df["merchant_id"].map(lambda v: clean_id(v, "MCH", 4))
    df = df[df["merchant_id"].notna()].copy()

    df["mcc"] = df["mcc"].map(clean_mcc)
    df["merchant_category"] = df["merchant_category"].map(
        lambda v: normalize_category(v, MERCHANT_CATEGORY_MAP, default="Retail - Other")
    )
    df["business_type"] = df["business_type"].map(
        lambda v: normalize_category(v, BUSINESS_TYPE_MAP, default="Individual")
    )
    df["city"] = df["city"].map(lambda v: normalize_category(v, CITY_MAP, default=None))
    df["state"] = df["state"].where(~df["state"].map(is_null_token), None)
    df["onboarding_date"] = df["onboarding_date"].map(parse_timestamp)
    df["merchant_status"] = df["merchant_status"].map(
        lambda v: normalize_category(v, MERCHANT_STATUS_MAP, default="ACTIVE")
    )

    ticket = df["declared_avg_ticket_size"].map(clean_amount)
    df["declared_avg_ticket_size"] = ticket.abs().round(2)
    df["declared_avg_ticket_size_was_negative"] = (ticket < 0).fillna(False)

    df["settlement_account"] = df["settlement_account"].where(
        ~df["settlement_account"].map(is_null_token), None
    )
    df["settlement_account_on_file"] = df["settlement_account"].notna()

    n_before_dedup = len(df)
    df["completeness"] = df.notna().sum(axis=1)
    df = df.sort_values(["completeness", "onboarding_date"], ascending=[False, True])
    df = df.drop_duplicates(subset="merchant_id", keep="first")
    n_after_dedup = len(df)

    # fill missing MCC from the most common code seen for the merchant's category
    mode_mcc_by_cat = (
        df.dropna(subset=["mcc"]).groupby("merchant_category")["mcc"]
        .agg(lambda s: s.value_counts().idxmax())
    )
    missing_mcc_mask = df["mcc"].isna()
    df.loc[missing_mcc_mask, "mcc"] = df.loc[missing_mcc_mask, "merchant_category"].map(mode_mcc_by_cat)
    df["mcc_imputed"] = missing_mcc_mask

    df = scrub_null_tokens(df)

    cols = [
        "merchant_id", "merchant_name", "mcc", "mcc_imputed", "merchant_category", "business_type",
        "city", "state", "onboarding_date", "settlement_account_on_file", "merchant_status",
        "declared_avg_ticket_size", "declared_avg_ticket_size_was_negative",
    ]
    df = df[cols].reset_index(drop=True)

    log("Merchants cleaning", (
        f"- Raw rows: {n_raw}\n"
        f"- Rows dropped for unrecoverable merchant_id: {n_raw - n_before_dedup}\n"
        f"- Duplicate merchant_id rows collapsed: {n_before_dedup - n_after_dedup}\n"
        f"- Final unique merchants: {n_after_dedup}\n"
        f"- MCC imputed from category mode (was missing/non-numeric): {df['mcc_imputed'].sum()}\n"
        f"- Declared avg ticket size values that were negative (sign corrected): {df['declared_avg_ticket_size_was_negative'].sum()}\n"
        f"- Merchants with no settlement account on file: {(~df['settlement_account_on_file']).sum()}\n"
    ))
    return df


# ---------------------------------------------------------------------------
# 3. UPI transactions
# ---------------------------------------------------------------------------

def clean_transactions(customer_ids, merchant_ids):
    df = pd.read_csv(RAW / "track1_upi_transactions.csv", dtype=str)
    df = strip_strings(df)
    n_raw = len(df)

    n_exact_dupes = df.duplicated().sum()
    df = df.drop_duplicates()

    df["txn_id"] = df["txn_id"].map(lambda v: clean_id(v, "TXN", 8))
    n_before_id_dedup = len(df)
    df = df[df["txn_id"].notna()]
    df = df.drop_duplicates(subset="txn_id", keep="first")
    n_after_id_dedup = len(df)

    df["timestamp"] = df["timestamp"].map(parse_timestamp)
    df["user_id"] = df["user_id"].map(lambda v: clean_id(v, "USR", 5))
    df["merchant_id"] = df["merchant_id"].map(lambda v: clean_id(v, "MCH", 4))

    amount = df["amount"].map(clean_amount)
    df["amount_was_negative"] = (amount < 0).fillna(False)
    df["amount"] = amount.abs().round(2)
    df["amount_missing"] = df["amount"].isna()

    utr_clean = df["utr"].map(clean_utr)
    df["utr"], df["utr_valid"] = zip(*utr_clean)
    df["utr_missing"] = df["utr"].isna()

    df["mcc"] = df["mcc"].map(clean_mcc)
    df["status"] = df["status"].map(lambda v: normalize_category(v, TXN_STATUS_MAP, default="PENDING"))

    df["user_id_valid_fk"] = df["user_id"].isin(customer_ids)
    df["merchant_id_valid_fk"] = df["merchant_id"].isin(merchant_ids)

    df = scrub_null_tokens(df)

    cols = [
        "txn_id", "timestamp", "user_id", "user_id_valid_fk", "merchant_id", "merchant_id_valid_fk",
        "amount", "amount_was_negative", "amount_missing", "utr", "utr_valid", "utr_missing",
        "mcc", "status",
    ]
    df = df[cols].reset_index(drop=True)

    log("Transactions cleaning", (
        f"- Raw rows: {n_raw}\n"
        f"- Exact duplicate rows removed: {n_exact_dupes}\n"
        f"- Rows dropped for unrecoverable txn_id: {(n_raw - n_exact_dupes) - n_before_id_dedup}\n"
        f"- Duplicate txn_id (after standardizing format) removed: {n_before_id_dedup - n_after_id_dedup}\n"
        f"- Final unique transactions: {len(df)}\n"
        f"- Amounts that were negative (sign corrected, flagged): {df['amount_was_negative'].sum()}\n"
        f"- Amounts unparseable/missing: {df['amount_missing'].sum()}\n"
        f"- UTR missing: {df['utr_missing'].sum()}\n"
        f"- UTR present but invalid format: {((~df['utr_valid']) & (~df['utr_missing'])).sum()}\n"
        f"- Transactions referencing a user_id not found in KYC master (invalid FK, kept & flagged): {(~df['user_id_valid_fk']).sum()}\n"
        f"- Transactions referencing a merchant_id not found in merchant master (invalid FK, kept & flagged): {(~df['merchant_id_valid_fk']).sum()}\n"
    ))
    return df


# ---------------------------------------------------------------------------
# 4. Chargebacks
# ---------------------------------------------------------------------------

def clean_chargebacks(txn_ids, customer_ids, merchant_ids):
    with open(RAW / "track1_chargebacks.json", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)
    # Also save a CSV copy of the raw (pre-cleaning) JSON records, purely as a
    # local convenience for tools/spreadsheets that prefer CSV - the actual
    # cleaning below still operates on the parsed JSON records directly.
    df.to_csv(RAW / "track1_chargebacks_converted.csv", index=False)
    df = strip_strings(df)
    n_raw = len(df)

    n_exact_dupes = df.duplicated(subset="complaint_id").sum()
    df = df.drop_duplicates(subset="complaint_id", keep="first")

    df["txn_id"] = df["txn_id"].map(lambda v: clean_id(v, "TXN", 8))
    df["user_id"] = df["user_id"].map(lambda v: clean_id(v, "USR", 5))
    df["merchant_id"] = df["merchant_id"].map(lambda v: clean_id(v, "MCH", 4))

    df["transaction_timestamp"] = df["transaction_timestamp"].map(parse_timestamp)
    df["reported_timestamp"] = df["reported_timestamp"].map(parse_timestamp)
    df["bank_response_timestamp"] = df["bank_response_timestamp"].map(parse_timestamp)

    reported_before_txn = df["reported_timestamp"] < df["transaction_timestamp"]
    bank_before_reported = df["bank_response_timestamp"] < df["reported_timestamp"]
    df["timestamps_logically_valid"] = ~(reported_before_txn.fillna(False) | bank_before_reported.fillna(False))

    delay = (df["reported_timestamp"] - df["transaction_timestamp"]).dt.days
    df["reporting_delay_days"] = delay.where(df["timestamps_logically_valid"])

    amount = df["disputed_amount"].map(clean_amount)
    df["disputed_amount_was_negative"] = (amount < 0).fillna(False)
    df["disputed_amount"] = amount.abs().round(2)
    df["disputed_amount_missing"] = df["disputed_amount"].isna()

    df["reason_code_raw"] = df["reason_code"]
    df["reason_code"] = df["reason_code"].map(lambda v: normalize_category(v, REASON_CODE_MAP, default="GENERAL_DISPUTE"))
    df["resolution_status"] = df["resolution_status"].map(
        lambda v: normalize_category(v, RESOLUTION_STATUS_MAP, default="OPEN")
    )
    df["severity"] = df["severity"].map(lambda v: normalize_category(v, SEVERITY_MAP, default="MEDIUM"))
    df["channel"] = df["channel"].map(lambda v: normalize_category(v, CHANNEL_MAP, default="APP"))

    df["txn_id_valid_fk"] = df["txn_id"].isin(txn_ids)
    df["user_id_valid_fk"] = df["user_id"].isin(customer_ids)
    df["merchant_id_valid_fk"] = df["merchant_id"].isin(merchant_ids)

    df = scrub_null_tokens(df, skip=("reason_code_raw",))

    cols = [
        "complaint_id", "txn_id", "txn_id_valid_fk", "user_id", "user_id_valid_fk",
        "merchant_id", "merchant_id_valid_fk", "transaction_timestamp", "reported_timestamp",
        "bank_response_timestamp", "timestamps_logically_valid", "reporting_delay_days",
        "disputed_amount", "disputed_amount_was_negative", "disputed_amount_missing",
        "reason_code", "reason_code_raw", "complaint_text", "resolution_status", "severity", "channel",
    ]
    df = df[cols].reset_index(drop=True)

    log("Chargebacks cleaning", (
        f"- Raw rows: {n_raw}\n"
        f"- Duplicate complaint_id rows removed: {n_exact_dupes}\n"
        f"- Final unique chargebacks: {len(df)}\n"
        f"- Disputed amount missing/unparseable: {df['disputed_amount_missing'].sum()}\n"
        f"- Disputed amount values that were negative (sign corrected): {df['disputed_amount_was_negative'].sum()}\n"
        f"- Chargebacks with a logically impossible timestamp sequence (reported before transaction, or bank response before reported) - kept, flagged, excluded from delay metric: {(~df['timestamps_logically_valid']).sum()}\n"
        f"- Chargebacks referencing a txn_id not found in the transaction fact table (invalid FK, kept & flagged): {(~df['txn_id_valid_fk']).sum()}\n"
        f"- Chargebacks referencing a user_id not found in KYC master (invalid FK, kept & flagged): {(~df['user_id_valid_fk']).sum()}\n"
        f"- Chargebacks referencing a merchant_id not found in merchant master (invalid FK, kept & flagged): {(~df['merchant_id_valid_fk']).sum()}\n"
        f"- Reason codes were consolidated from 33 raw free-text/code variants into 7 canonical fraud/dispute categories (see reports/cleaning_mapping_reference.md).\n"
        f"- Raw JSON also saved as `data/raw/track1_chargebacks_converted.csv` (pre-cleaning, local-only convenience copy for spreadsheet/CSV tooling).\n"
    ))
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("Data Quality & Cleaning Report")
    report_lines.append(
        "Generated by `scripts/clean_pipeline.py`. Every transformation below is reversible / "
        "auditable against the raw files in `data/raw/`. No row is dropped solely for being "
        "\"messy\" - rows are only removed when a stable identifier cannot be recovered at all, "
        "or when they are exact duplicates. Everything else is standardized and, where the raw "
        "value could not be trusted, flagged with an explicit boolean column instead of being "
        "silently discarded.\n"
    )

    customers = clean_kyc()
    merchants = clean_merchants()
    customer_ids = set(customers["user_id"])
    merchant_ids = set(merchants["merchant_id"])

    transactions = clean_transactions(customer_ids, merchant_ids)
    txn_ids = set(transactions["txn_id"])

    chargebacks = clean_chargebacks(txn_ids, customer_ids, merchant_ids)

    customers.to_csv(OUT / "dim_customers.csv", index=False)
    merchants.to_csv(OUT / "dim_merchants.csv", index=False)
    transactions.to_csv(OUT / "fact_transactions.csv", index=False)
    chargebacks.to_csv(OUT / "fact_chargebacks.csv", index=False)

    log("Output files", (
        f"- `data/cleaned/dim_customers.csv` - {len(customers)} rows\n"
        f"- `data/cleaned/dim_merchants.csv` - {len(merchants)} rows\n"
        f"- `data/cleaned/fact_transactions.csv` - {len(transactions)} rows\n"
        f"- `data/cleaned/fact_chargebacks.csv` - {len(chargebacks)} rows\n"
    ))

    (REPORTS / "data_quality_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
