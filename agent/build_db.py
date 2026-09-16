"""
Loads the cleaned star schema (data/cleaned/*.csv) into a local SQLite
database (agent/analytics.db) for the Text-to-SQL agent.

Run: python3 agent/build_db.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEANED = ROOT / "data" / "cleaned"
DB_PATH = Path(__file__).resolve().parent / "analytics.db"

# Boolean flag columns come out of the CSVs as the strings "True"/"False";
# SQLite has no native boolean, so these are stored as 0/1 integers so
# `WHERE merchant_id_valid_fk = 1` works naturally in generated SQL.
BOOL_COLS = {
    "dim_customers": ["pan_valid", "aadhaar_valid", "income_was_negative", "income_missing"],
    "dim_merchants": ["mcc_imputed", "settlement_account_on_file", "declared_avg_ticket_size_was_negative"],
    "fact_transactions": [
        "user_id_valid_fk", "merchant_id_valid_fk", "amount_was_negative",
        "amount_missing", "utr_valid", "utr_missing",
    ],
    "fact_chargebacks": [
        "txn_id_valid_fk", "user_id_valid_fk", "merchant_id_valid_fk",
        "timestamps_logically_valid", "disputed_amount_was_negative", "disputed_amount_missing",
    ],
}

TABLES = ["dim_customers", "dim_merchants", "fact_transactions", "fact_chargebacks"]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_txn_user ON fact_transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_txn_merchant ON fact_transactions(merchant_id)",
    "CREATE INDEX IF NOT EXISTS idx_txn_timestamp ON fact_transactions(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_cb_txn ON fact_chargebacks(txn_id)",
    "CREATE INDEX IF NOT EXISTS idx_cb_user ON fact_chargebacks(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_cb_merchant ON fact_chargebacks(merchant_id)",
]


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    for table in TABLES:
        df = pd.read_csv(CLEANED / f"{table}.csv")
        for col in BOOL_COLS.get(table, []):
            if col in df.columns:
                df[col] = df[col].map({"True": 1, "False": 0, True: 1, False: 0}).astype("Int64")
        df.to_sql(table, conn, if_exists="replace", index=False)
        print(f"  loaded {table}: {len(df):,} rows, {len(df.columns)} columns")
    cur = conn.cursor()
    for stmt in INDEXES:
        cur.execute(stmt)
    conn.commit()
    conn.close()
    print(f"Built {DB_PATH}")


if __name__ == "__main__":
    main()
