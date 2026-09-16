"""
Generates a native Power BI Project (PBIP: TMDL semantic model + report) from
the cleaned star schema in data/cleaned/. This is the code-authored equivalent
of File > Get Data + Manage Relationships + New Measure + drag-and-drop visuals
in Power BI Desktop -- written as text so it's versionable and reproducible,
per dashboard/powerbi_guide.md.

Run: python3 scripts/build_powerbi_project.py
Then open powerbi/UPI_Fraud_Analytics.pbip in Power BI Desktop and hit Refresh.

If the project folder is ever moved to a different machine/path, update the
`DataFolder` expression's value in Power BI Desktop (Transform data > Manage
Parameters, or Transform data > right-click "DataFolder" query > Advanced
Editor) to point at the new data/cleaned/ location, then Refresh.
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI_DIR = ROOT / "powerbi"
PROJECT = "UPI_Fraud_Analytics"
REPORT_DIR = PBI_DIR / f"{PROJECT}.Report"
MODEL_DIR = PBI_DIR / f"{PROJECT}.SemanticModel"

# Absolute path baked in as the default value of the DataFolder parameter so
# the project works immediately, with zero manual setup, on this machine.
WIN_DATA_FOLDER = r"C:\Users\Asuna\Documents\Datathon\data\cleaned"


def g():
    return str(uuid.uuid4())


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, obj):
    write(path, json.dumps(obj, indent=2))


# ---------------------------------------------------------------------------
# Table schemas: (column_name, power_query_type, tmdl_dataType, formatString, summarizeBy)
# ---------------------------------------------------------------------------

DIM_CUSTOMERS_COLS = [
    ("user_id", "type text", "string", None, "none"),
    ("full_name", "type text", "string", None, "none"),
    ("pan_masked", "type text", "string", None, "none"),
    ("pan_valid", "type logical", "boolean", None, "none"),
    ("aadhaar_masked", "type text", "string", None, "none"),
    ("aadhaar_valid", "type logical", "boolean", None, "none"),
    ("date_of_birth", "type date", "dateTime", "Short Date", "none"),
    ("city", "type text", "string", None, "none"),
    ("state", "type text", "string", None, "none"),
    ("monthly_income", "type number", "double", "\u20b9#,0.00", "sum"),
    ("income_was_negative", "type logical", "boolean", None, "none"),
    ("income_missing", "type logical", "boolean", None, "none"),
    ("occupation", "type text", "string", None, "none"),
    ("signup_timestamp", "type datetime", "dateTime", "General Date", "none"),
    ("kyc_status", "type text", "string", None, "none"),
    ("risk_segment", "type text", "string", None, "none"),
    ("risk_segment_missing", "type logical", "boolean", None, "none"),
]

DIM_MERCHANTS_COLS = [
    ("merchant_id", "type text", "string", None, "none"),
    ("merchant_name", "type text", "string", None, "none"),
    ("mcc", "type text", "string", None, "none"),
    ("mcc_imputed", "type logical", "boolean", None, "none"),
    ("merchant_category", "type text", "string", None, "none"),
    ("business_type", "type text", "string", None, "none"),
    ("city", "type text", "string", None, "none"),
    ("state", "type text", "string", None, "none"),
    ("onboarding_date", "type datetime", "dateTime", "General Date", "none"),
    ("settlement_account_on_file", "type logical", "boolean", None, "none"),
    ("merchant_status", "type text", "string", None, "none"),
    ("declared_avg_ticket_size", "type number", "double", "\u20b9#,0.00", "sum"),
    ("declared_avg_ticket_size_was_negative", "type logical", "boolean", None, "none"),
]

FACT_TRANSACTIONS_COLS = [
    ("txn_id", "type text", "string", None, "none"),
    ("timestamp", "type datetime", "dateTime", "General Date", "none"),
    ("user_id", "type text", "string", None, "none"),
    ("user_id_valid_fk", "type logical", "boolean", None, "none"),
    ("merchant_id", "type text", "string", None, "none"),
    ("merchant_id_valid_fk", "type logical", "boolean", None, "none"),
    ("amount", "type number", "double", "\u20b9#,0.00", "sum"),
    ("amount_was_negative", "type logical", "boolean", None, "none"),
    ("amount_missing", "type logical", "boolean", None, "none"),
    ("utr", "type text", "string", None, "none"),
    ("utr_valid", "type logical", "boolean", None, "none"),
    ("utr_missing", "type logical", "boolean", None, "none"),
    ("mcc", "type text", "string", None, "none"),
    ("status", "type text", "string", None, "none"),
]

FACT_CHARGEBACKS_COLS = [
    ("complaint_id", "type text", "string", None, "none"),
    ("txn_id", "type text", "string", None, "none"),
    ("txn_id_valid_fk", "type logical", "boolean", None, "none"),
    ("user_id", "type text", "string", None, "none"),
    ("user_id_valid_fk", "type logical", "boolean", None, "none"),
    ("merchant_id", "type text", "string", None, "none"),
    ("merchant_id_valid_fk", "type logical", "boolean", None, "none"),
    ("transaction_timestamp", "type datetime", "dateTime", "General Date", "none"),
    ("reported_timestamp", "type datetime", "dateTime", "General Date", "none"),
    ("bank_response_timestamp", "type datetime", "dateTime", "General Date", "none"),
    ("timestamps_logically_valid", "type logical", "boolean", None, "none"),
    ("reporting_delay_days", "type number", "double", "#,0.0", "average"),
    ("disputed_amount", "type number", "double", "\u20b9#,0.00", "sum"),
    ("disputed_amount_was_negative", "type logical", "boolean", None, "none"),
    ("disputed_amount_missing", "type logical", "boolean", None, "none"),
    ("reason_code", "type text", "string", None, "none"),
    ("reason_code_raw", "type text", "string", None, "none"),
    ("complaint_text", "type text", "string", None, "none"),
    ("resolution_status", "type text", "string", None, "none"),
    ("severity", "type text", "string", None, "none"),
    ("channel", "type text", "string", None, "none"),
]

TABLES = [
    ("dim_customers", DIM_CUSTOMERS_COLS),
    ("dim_merchants", DIM_MERCHANTS_COLS),
    ("fact_transactions", FACT_TRANSACTIONS_COLS),
    ("fact_chargebacks", FACT_CHARGEBACKS_COLS),
]

MEASURES = [
    ("Total Transactions", "COUNTROWS(fact_transactions)", "#,0"),
    ("Total Txn Amount", "SUM(fact_transactions[amount])", "\u20b9#,0.00"),
    ("Total Txn Amount (Success)", 'CALCULATE([Total Txn Amount], fact_transactions[status] = "SUCCESS")', "\u20b9#,0.00"),
    ("Avg Txn Value", "AVERAGE(fact_transactions[amount])", "\u20b9#,0.00"),
    ("Avg Txn Value (Success)", 'CALCULATE([Avg Txn Value], fact_transactions[status] = "SUCCESS")', "\u20b9#,0.00"),
    ("Success Rate", 'DIVIDE(CALCULATE([Total Transactions], fact_transactions[status] = "SUCCESS"), [Total Transactions])', "0.00%"),
    ("Failed Rate", 'DIVIDE(CALCULATE([Total Transactions], fact_transactions[status] = "FAILED"), [Total Transactions])', "0.00%"),
    ("Pending Rate", 'DIVIDE(CALCULATE([Total Transactions], fact_transactions[status] = "PENDING"), [Total Transactions])', "0.00%"),
    ("Transactions Missing UTR", "CALCULATE([Total Transactions], fact_transactions[utr_missing] = TRUE)", "#,0"),
    ("Transactions Missing UTR Rate", "DIVIDE([Transactions Missing UTR], [Total Transactions])", "0.00%"),
    ("Transactions Missing/Invalid UTR Rate", "DIVIDE([Transactions Missing UTR] + [Transactions Invalid UTR], [Total Transactions])", "0.00%"),
    ("Transactions Invalid UTR", "CALCULATE([Total Transactions], fact_transactions[utr_valid] = FALSE, fact_transactions[utr_missing] = FALSE)", "#,0"),
    ("Chargeback Count", "COUNTROWS(fact_chargebacks)", "#,0"),
    ("Chargeback Amount", "SUM(fact_chargebacks[disputed_amount])", "\u20b9#,0.00"),
    ("CB to Txn Ratio (Count)", "DIVIDE([Chargeback Count], [Total Transactions])", "0.00%"),
    ("CB to Txn Ratio (Amount)", "DIVIDE([Chargeback Amount], [Total Txn Amount])", "0.00%"),
    ("Avg Dispute Delay (Days)", "CALCULATE(AVERAGE(fact_chargebacks[reporting_delay_days]), fact_chargebacks[timestamps_logically_valid] = TRUE)", "#,0.0"),
    ("Avg Dispute Delay (Days, All)", "AVERAGE(fact_chargebacks[reporting_delay_days])", "#,0.0"),
    ("Disputes Reported After 7d", "CALCULATE([Chargeback Count], fact_chargebacks[reporting_delay_days] > 7)", "#,0"),
    ("Disputes Reported After 7d Rate", "DIVIDE([Disputes Reported After 7d], [Chargeback Count])", "0.00%"),
    ("KYC Completion Rate", 'DIVIDE(CALCULATE(COUNTROWS(dim_customers), dim_customers[kyc_status] = "VERIFIED"), COUNTROWS(dim_customers))', "0.00%"),
    ("KYC Rejection Rate", 'DIVIDE(CALCULATE(COUNTROWS(dim_customers), dim_customers[kyc_status] = "REJECTED"), COUNTROWS(dim_customers))', "0.00%"),
    ("Total Customers", "COUNTROWS(dim_customers)", "#,0"),
    ("Total Merchants", "COUNTROWS(dim_merchants)", "#,0"),
    ("Txn User FK Match Rate", "DIVIDE(CALCULATE([Total Transactions], fact_transactions[user_id_valid_fk] = TRUE), [Total Transactions])", "0.00%"),
    ("Txn Merchant FK Match Rate", "DIVIDE(CALCULATE([Total Transactions], fact_transactions[merchant_id_valid_fk] = TRUE), [Total Transactions])", "0.00%"),
    ("CB Txn FK Match Rate", "DIVIDE(CALCULATE([Chargeback Count], fact_chargebacks[txn_id_valid_fk] = TRUE), [Chargeback Count])", "0.00%"),
    ("CB on Unmatched Merchant (Count)", "CALCULATE([Chargeback Count], fact_chargebacks[merchant_id_valid_fk] = FALSE)", "#,0"),
    ("CB on Unmatched Merchant (Amount)", "CALCULATE([Chargeback Amount], fact_chargebacks[merchant_id_valid_fk] = FALSE)", "\u20b9#,0.00"),
    (
        "Merchant CB to Txn Ratio",
        "VAR CB = CALCULATE([Chargeback Count], fact_chargebacks[merchant_id_valid_fk] = TRUE)\n"
        "\t\t\tVAR TXN = CALCULATE([Total Transactions], fact_transactions[merchant_id_valid_fk] = TRUE)\n"
        "\t\t\tRETURN\n"
        "\t\t\t\tDIVIDE(CB, TXN)",
        "0.00%",
    ),
    (
        "High Risk Users (2+ Disputes)",
        'COUNTROWS(FILTER(SUMMARIZE(fact_chargebacks, fact_chargebacks[user_id], "CBCount", CALCULATE(COUNTROWS(fact_chargebacks))), [CBCount] >= 2))',
        "#,0",
    ),
    (
        "High Risk Merchants (2+ Disputes)",
        'COUNTROWS(FILTER(SUMMARIZE(fact_chargebacks, fact_chargebacks[merchant_id], "CBCount", CALCULATE(COUNTROWS(fact_chargebacks))), [CBCount] >= 2))',
        "#,0",
    ),
    ("Users With Disputes", "DISTINCTCOUNT(fact_chargebacks[user_id])", "#,0"),
    (
        "Merchant-Day Spikes (2+ Txns)",
        'COUNTROWS(FILTER(SUMMARIZE(fact_transactions, fact_transactions[merchant_id], fact_transactions[TxnDate], "TxnCount", CALCULATE(COUNTROWS(fact_transactions))), [TxnCount] >= 2))',
        "#,0",
    ),
]

# Trend-delta KPI cards: first half vs second half of the observed window,
# rendered as a single "▲ 12.3%" text measure -- mirrors the HTML dashboard's
# mini trend indicators without needing a marked date table / time
# intelligence functions (DATEADD etc.), which this model deliberately
# doesn't set up (see DateTable comments).
def _trend_measure(name, agg_dax, date_col, date_table):
    return (
        name,
        f"VAR MinD = CALCULATE(MIN({date_table}[{date_col}]))\n"
        f"\t\t\tVAR MaxD = CALCULATE(MAX({date_table}[{date_col}]))\n"
        "\t\t\tVAR Mid = MinD + INT((MaxD - MinD) / 2)\n"
        f"\t\t\tVAR FirstHalf = CALCULATE({agg_dax}, {date_table}[{date_col}] <= Mid)\n"
        f"\t\t\tVAR SecondHalf = CALCULATE({agg_dax}, {date_table}[{date_col}] > Mid)\n"
        "\t\t\tVAR Pct = DIVIDE(SecondHalf - FirstHalf, FirstHalf)\n"
        '\t\t\tRETURN IF(ISBLANK(Pct), "—", IF(Pct >= 0, "▲ " & FORMAT(Pct, "0.0%"), "▼ " & FORMAT(ABS(Pct), "0.0%")) & " vs 1st half")',
        None,
    )


MEASURES += [
    _trend_measure("Txn Volume Trend", "[Total Transactions]", "TxnDate", "fact_transactions"),
    _trend_measure("Txn Value Trend", "[Total Txn Amount]", "TxnDate", "fact_transactions"),
    _trend_measure("Success Rate Trend", "[Success Rate]", "TxnDate", "fact_transactions"),
    _trend_measure("Failed Rate Trend", "[Failed Rate]", "TxnDate", "fact_transactions"),
]


# ---------------------------------------------------------------------------
# TMDL generation
# ---------------------------------------------------------------------------

def m_partition_block(table_name: str, cols, derived_date_col=None) -> str:
    # derived_date_col: optional (source_column_name, new_column_name) to add a
    # date-only column via Power Query (NOT a DAX calculated column) so it's a
    # first-pass column usable as a relationship endpoint.
    n = len(cols)
    type_pairs = ", ".join(f'{{"{c[0]}", {c[1]}}}' for c in cols)
    file_ref = 'DataFolder & "\\' + table_name + '.csv"'
    steps = [
        f'    Source = Csv.Document(File.Contents({file_ref}),[Delimiter=",", Columns={n}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{{{type_pairs}}}, "en-US"),',
    ]
    prev = '#"Changed Type"'
    if derived_date_col:
        src_col, new_col = derived_date_col
        step_name = f'#"Added {new_col}"'
        steps.append(
            f'    {step_name} = Table.AddColumn({prev}, "{new_col}", each try Date.From([{src_col}]) otherwise null, type date),'
        )
        prev = step_name
    steps.append(
        f'    #"Errors Replaced" = Table.ReplaceErrorValues({prev}, List.Transform(Table.ColumnNames({prev}), each {{_, null}}))'
    )
    body = "\n\t\t\t\t".join(["let"] + steps + ["in", '    #"Errors Replaced"'])
    lines = [
        f"\tpartition {table_name} = m",
        "\t\tmode: import",
        "\t\tsource =",
        f"\t\t\t\t{body}",
    ]
    return "\n".join(lines) + "\n"


def column_block(name, dtype, fmt, summarize) -> str:
    lines = [f"\tcolumn {name}", f"\t\tdataType: {dtype}"]
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tlineageTag: {g()}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append(f"\t\tsourceColumn: {name}")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def calc_column_block(name, dax, dtype, fmt, summarize) -> str:
    # Regular DAX calculated column. Safe as long as it is NEVER used as a
    # relationship endpoint (see DateTable/TxnDate/ReportedDate comments above
    # for why that specific combination breaks PBIP loading).
    if "\n" in dax:
        lines = [f"\tcolumn {name} =", f"\t\t\t{dax}"]
    else:
        lines = [f"\tcolumn {name} = {dax}"]
    lines.append(f"\t\tdataType: {dtype}")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tlineageTag: {g()}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append("\t\tisDataTypeInferred")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def measure_block(name, dax, fmt) -> str:
    quoted = f"'{name}'"
    if "\n" in dax:
        lines = [f"\tmeasure {quoted} =", f"\t\t\t{dax}"]
    else:
        lines = [f"\tmeasure {quoted} = {dax}"]
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tlineageTag: {g()}")
    lines.append("")
    return "\n".join(lines)


DERIVED_DATE_COLS = {
    "fact_transactions": ("timestamp", "TxnDate"),
    "fact_chargebacks": ("reported_timestamp", "ReportedDate"),
}

# One-click "insight" filter columns: each pre-computes a multi-step analytical
# question (e.g. "is this a repeat-dispute customer?") into a single field, so
# a slicer click filters the whole page instead of requiring a sorted table.
# These are plain DAX calculated columns, never used as relationship
# endpoints, so they don't hit the two-pass loading issue documented above.
# Power BI's Import-mode engine auto-inserts one synthetic "blank" row into
# any table that is the "one" side of a relationship with unmatched foreign
# keys (dim_customers/dim_merchants: ~52-68% of transactions/chargebacks
# don't match; fact_transactions itself: ~7% of chargebacks' txn_id doesn't
# match a transaction). That phantom row has BLANK() for every column, so it
# surfaces as an unexplained "(Blank)" entry in every slicer/chart built on
# those tables - even though the *real* source data has no nulls there. The
# *_Display columns below wrap the affected raw columns with a readable label
# for that phantom row (and, for risk_segment, also for genuinely missing
# data on real rows) instead of a bare, confusing "(Blank)". Report pages use
# these *_Display columns instead of the raw ones wherever they're shown to
# a user (see build_pages()); the raw columns are left untouched for anyone
# querying the model directly.
EXTRA_CALC_COLUMNS = {
    "dim_customers": [
        (
            "DisputeRiskFlag",
            'IF(ISBLANK(dim_customers[user_id]), "No Matching Customer", '
            "VAR CB = COUNTROWS(RELATEDTABLE(fact_chargebacks)) "
            'RETURN SWITCH(TRUE(), CB >= 2, "Repeat (2+) Disputes", CB = 1, "Single Dispute", "No Disputes"))',
            "string",
            None,
            "none",
        ),
        (
            "KycStatusDisplay",
            'IF(ISBLANK(dim_customers[kyc_status]) || dim_customers[kyc_status] = "", '
            '"No Matching Customer", dim_customers[kyc_status])',
            "string",
            None,
            "none",
        ),
        (
            "RiskSegmentDisplay",
            'IF(ISBLANK(dim_customers[user_id]), "No Matching Customer", '
            'IF(ISBLANK(dim_customers[risk_segment]) || dim_customers[risk_segment] = "", "Not Provided", '
            "dim_customers[risk_segment]))",
            "string",
            None,
            "none",
        ),
        (
            "StateDisplay",
            'IF(ISBLANK(dim_customers[state]) || dim_customers[state] = "", '
            '"No Matching Customer", dim_customers[state])',
            "string",
            None,
            "none",
        ),
        (
            "CityDisplay",
            'IF(ISBLANK(dim_customers[city]) || dim_customers[city] = "", '
            '"No Matching Customer", dim_customers[city])',
            "string",
            None,
            "none",
        ),
    ],
    "dim_merchants": [
        (
            "DisputeRiskFlag",
            'IF(ISBLANK(dim_merchants[merchant_id]), "No Matching Merchant", '
            "VAR CB = COUNTROWS(RELATEDTABLE(fact_chargebacks)) "
            'RETURN SWITCH(TRUE(), CB >= 2, "Repeat (2+) Disputes", CB = 1, "Single Dispute", "No Disputes"))',
            "string",
            None,
            "none",
        ),
        (
            "HadSpikeDay",
            'IF(ISBLANK(dim_merchants[merchant_id]), "No Matching Merchant", '
            "VAR T = RELATEDTABLE(fact_transactions)\n"
            "\t\t\tVAR SpikeDays = COUNTROWS(FILTER(SUMMARIZE(T, fact_transactions[TxnDate], \"C\", COUNTROWS(fact_transactions)), [C] >= 2))\n"
            '\t\t\tRETURN IF(SpikeDays > 0, "Spike Day (2+ same-day txns)", "Normal"))',
            "string",
            None,
            "none",
        ),
        (
            "MerchantCategoryDisplay",
            'IF(ISBLANK(dim_merchants[merchant_category]) || dim_merchants[merchant_category] = "", '
            '"No Matching Merchant", dim_merchants[merchant_category])',
            "string",
            None,
            "none",
        ),
        (
            "MerchantStatusDisplay",
            'IF(ISBLANK(dim_merchants[merchant_status]) || dim_merchants[merchant_status] = "", '
            '"No Matching Merchant", dim_merchants[merchant_status])',
            "string",
            None,
            "none",
        ),
        (
            "MerchantNameDisplay",
            'IF(ISBLANK(dim_merchants[merchant_name]) || dim_merchants[merchant_name] = "", '
            '"No Matching Merchant", dim_merchants[merchant_name])',
            "string",
            None,
            "none",
        ),
    ],
    "fact_transactions": [
        (
            "UTRProblem",
            'IF(ISBLANK(fact_transactions[txn_id]), "No Matching Transaction", '
            'IF(fact_transactions[utr_missing] = TRUE || fact_transactions[utr_valid] = FALSE, "Missing/Invalid", "OK"))',
            "string",
            None,
            "none",
        ),
        (
            "StatusDisplay",
            'IF(ISBLANK(fact_transactions[status]) || fact_transactions[status] = "", '
            '"No Matching Transaction", fact_transactions[status])',
            "string",
            None,
            "none",
        ),
    ],
    "fact_chargebacks": [
        (
            "DelayBucket",
            "SWITCH(TRUE(), "
            "ISBLANK(fact_chargebacks[reporting_delay_days]), \"Unknown\", "
            'fact_chargebacks[reporting_delay_days] <= 0, "Same day", '
            'fact_chargebacks[reporting_delay_days] <= 3, "1-3 days", '
            'fact_chargebacks[reporting_delay_days] <= 7, "4-7 days", '
            '"8+ days")',
            "string",
            None,
            "none",
        ),
    ],
}


def build_table_tmdl(name, cols) -> str:
    out = [f"table {name}", f"\tlineageTag: {g()}", ""]
    for col_name, pq_type, dtype, fmt, summarize in cols:
        out.append(column_block(col_name, dtype, fmt, summarize))
    derived = DERIVED_DATE_COLS.get(name)
    if derived:
        _, new_col = derived
        out.append(column_block(new_col, "dateTime", "Short Date", "none"))
    out.append(m_partition_block(name, cols, derived_date_col=derived))
    for extra_name, dax, dtype, fmt, summarize in EXTRA_CALC_COLUMNS.get(name, []):
        out.append(calc_column_block(extra_name, dax, dtype, fmt, summarize))
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def build_date_table_tmdl() -> str:
    # Built entirely in Power Query (M), not DAX CALENDAR()/calculated columns,
    # so every column resolves in the same first pass as the other tables --
    # calculated tables/columns resolve in a later pass and can't reliably be
    # used as relationship endpoints in a freshly-authored TMDL project.
    out = [f"table DateTable", f"\tlineageTag: {g()}", ""]
    out.append(column_block("Date", "dateTime", "Short Date", "none"))
    out.append(column_block("Year", "int64", "0", "none"))
    out.append(column_block("Quarter", "string", None, "none"))
    out.append(column_block("MonthNumber", "int64", "0", "none"))
    out.append(column_block("MonthName", "string", None, "none"))
    out.append(column_block("YearMonth", "string", None, "none"))
    out.append(column_block("DayName", "string", None, "none"))

    m_steps = [
        "    StartDate = #date(2023,1,1),",
        "    EndDate = #date(2026,12,31),",
        "    NumberOfDays = Duration.Days(EndDate - StartDate) + 1,",
        "    DateList = List.Dates(StartDate, NumberOfDays, #duration(1,0,0,0)),",
        '    #"Converted to Table" = Table.FromList(DateList, Splitter.SplitByNothing(), {"Date"}, null, ExtraValues.Error),',
        '    #"Changed Type" = Table.TransformColumnTypes(#"Converted to Table",{{"Date", type date}}),',
        '    #"Added Year" = Table.AddColumn(#"Changed Type", "Year", each Date.Year([Date]), Int64.Type),',
        '    #"Added Quarter" = Table.AddColumn(#"Added Year", "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date])), type text),',
        '    #"Added MonthNumber" = Table.AddColumn(#"Added Quarter", "MonthNumber", each Date.Month([Date]), Int64.Type),',
        '    #"Added MonthName" = Table.AddColumn(#"Added MonthNumber", "MonthName", each Date.ToText([Date], "MMM"), type text),',
        '    #"Added YearMonth" = Table.AddColumn(#"Added MonthName", "YearMonth", each Date.ToText([Date], "yyyy-MM"), type text),',
        '    #"Added DayName" = Table.AddColumn(#"Added YearMonth", "DayName", each Date.ToText([Date], "ddd"), type text)',
    ]
    body = "\n\t\t\t\t".join(["let"] + m_steps + ["in", '    #"Added DayName"'])
    out.append(
        "\tpartition DateTable = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        f"\t\t\t\t{body}\n"
    )
    out.append("\tannotation __PBI_TimeIntelligenceEnabled = 1")
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def build_merchant_spike_table_tmdl() -> str:
    # "Suspicious transaction clusters" / "merchants with sudden transaction
    # spikes": every merchant-day with 2+ transactions, which is anomalous
    # against this population's ~1-txn/90-day norm (see business_metrics_summary.md).
    # A calculated table, but its columns are NEVER used as a relationship
    # endpoint -- merchant name/category are pulled in via LOOKUPVALUE (which
    # needs no relationship at all), not RELATED, specifically to avoid the
    # calculated-table-as-relationship-endpoint issue documented above.
    out = [f"table MerchantSpikeDays", f"\tlineageTag: {g()}", ""]
    out.append(column_block("merchant_id", "string", None, "none"))
    out.append(column_block("MerchantName", "string", None, "none"))
    out.append(column_block("MerchantCategory", "string", None, "none"))
    out.append(column_block("TxnDate", "dateTime", "Short Date", "none"))
    out.append(column_block("TxnCount", "int64", "#,0", "none"))

    dax = (
        "VAR Spikes =\n"
        "\t\t\t\tFILTER(\n"
        "\t\t\t\t\tSUMMARIZE(fact_transactions, fact_transactions[merchant_id], fact_transactions[TxnDate], \"TxnCount\", COUNTROWS(fact_transactions)),\n"
        "\t\t\t\t\t[TxnCount] >= 2\n"
        "\t\t\t\t)\n"
        "\t\t\tRETURN\n"
        "\t\t\t\tADDCOLUMNS(\n"
        "\t\t\t\t\tSpikes,\n"
        '\t\t\t\t\t"MerchantName", LOOKUPVALUE(dim_merchants[merchant_name], dim_merchants[merchant_id], [merchant_id]),\n'
        '\t\t\t\t\t"MerchantCategory", LOOKUPVALUE(dim_merchants[merchant_category], dim_merchants[merchant_id], [merchant_id])\n'
        "\t\t\t\t)"
    )
    out.append(
        "\tpartition MerchantSpikeDays = calculated\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        f"\t\t\t{dax}\n"
    )
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


# Plain-English definition for every KPI/measure used anywhere in the
# report, for the "KPI Reference" page. A static DAX table (DATATABLE), not
# a relationship endpoint, so it carries none of the earlier
# calculated-table/relationship risk -- it's purely a reference list.
# Five columns per the "KPI Dictionary" spec: KpiName, Formula (exact DAX
# where it's short enough to read in a table cell, otherwise a plain-English
# statement of the logic -- both are explicitly "Formula / Logic"), DataSource
# (which cleaned table(s) it's built from), UpdateFrequency, and Owner
# (assigned by category -- a role/team, never a fabricated individual name).
KPI_DICTIONARY = [
    ("Total Transactions", "COUNTROWS(fact_transactions)", "fact_transactions", "On report republish", "Business Operations"),
    ("Total Txn Amount", "SUM(fact_transactions[amount])", "fact_transactions", "On report republish", "Business Operations"),
    ("Avg Txn Value", "AVERAGE(fact_transactions[amount])", "fact_transactions", "On report republish", "Business Operations"),
    ("Success Rate", 'Share of transactions where status = "SUCCESS"', "fact_transactions", "On report republish", "Business Operations"),
    ("Failed Rate", 'Share of transactions where status = "FAILED"', "fact_transactions", "On report republish", "Business Operations"),
    ("Pending Rate", 'Share of transactions where status = "PENDING"', "fact_transactions", "On report republish", "Business Operations"),
    ("Chargeback Count", "COUNTROWS(fact_chargebacks)", "fact_chargebacks", "On report republish", "Risk & Fraud Team"),
    ("Chargeback Amount", "SUM(fact_chargebacks[disputed_amount])", "fact_chargebacks", "On report republish", "Risk & Fraud Team"),
    ("CB to Txn Ratio", "DIVIDE([Chargeback Count], [Total Transactions])", "fact_chargebacks + fact_transactions", "On report republish", "Risk & Fraud Team"),
    ("Avg Dispute Delay (Days)", "Average reporting_delay_days, restricted to chargebacks with logically valid timestamps", "fact_chargebacks", "On report republish", "Risk & Fraud Team"),
    ("Disputes Reported After 7d", "Count of chargebacks where reporting_delay_days > 7", "fact_chargebacks", "On report republish", "Risk & Fraud Team"),
    ("High Risk Merchants (2+ Disputes)", "Count of distinct merchants with 2 or more chargeback rows", "fact_chargebacks", "On report republish", "Risk & Fraud Team"),
    ("Merchant-Day Spikes (2+ Txns)", "Count of merchant/day pairs with 2 or more transaction rows", "fact_transactions", "On report republish", "Risk & Fraud Team"),
    ("KYC Completion Rate", 'Share of customers where kyc_status = "VERIFIED"', "dim_customers", "On report republish", "Compliance Team"),
    ("KYC Rejection Rate", 'Share of customers where kyc_status = "REJECTED"', "dim_customers", "On report republish", "Compliance Team"),
    ("Txn User FK Match Rate", "Share of transactions where user_id_valid_fk = TRUE", "fact_transactions + dim_customers", "On report republish", "Data Engineering"),
    ("Txn Merchant FK Match Rate", "Share of transactions where merchant_id_valid_fk = TRUE", "fact_transactions + dim_merchants", "On report republish", "Data Engineering"),
    ("Transactions Missing/Invalid UTR Rate", "Share of transactions with a missing or malformed UPI transaction reference", "fact_transactions", "On report republish", "Data Engineering"),
]

# Static reference content for the KPI Reference page's left-panel FAQ list
# -- factually scoped to how *this* project actually works (batch-built,
# republish-to-refresh, one shared data source), not generic boilerplate.
FAQ_ENTRIES = [
    ("How often are these KPIs updated?", "This report is a static batch build. Numbers change only when the underlying script is rerun and the file is republished -- there is no live/scheduled refresh."),
    ("What's the difference between MoM and YoY growth?", "Month-over-month compares this period to the one right before it; year-over-year compares it to the same period a year ago. This report shows a first-half vs. second-half trend instead, since the dataset covers one fixed window rather than multiple calendar years."),
    ("How are risk thresholds like '2+ disputes' decided?", "They're fixed business rules chosen for this project, not statistically derived cutoffs -- see the Formula/Logic column alongside for the exact rule behind each metric."),
    ("Why do some KPIs exclude unmatched transactions?", "Match-rate KPIs deliberately separate out transactions with no matching customer/merchant record, since blending them in would understate how often the join genuinely succeeds."),
    ("Which numbers can I trust to match the chatbot?", "All of them -- the chatbot and this report read the exact same four cleaned CSV files, so there is only one source of truth in this project."),
    ("Who do I ask if a number looks wrong?", "Check the Formula/Logic column first. If the logic matches your expectation but the value still looks off, that's a data-pipeline question (scripts/clean_pipeline.py), not a report question."),
]


def _datatable_tmdl(table_name, col_defs, rows):
    # Shared builder for a small static reference table via DAX DATATABLE --
    # col_defs: [(name, dtype)]; rows: list of tuples matching col_defs order.
    # Never used as a relationship endpoint, so it's exempt from the
    # blank-row/two-pass-loading issues documented on the fact/dim tables.
    out = [f"table {table_name}", f"\tlineageTag: {g()}", ""]
    for col_name, _ in col_defs:
        out.append(column_block(col_name, "string", None, "none"))

    def esc(s):
        return str(s).replace('"', '""')

    row_strs = ",\n\t\t\t\t".join(
        "{" + ", ".join(f'"{esc(v)}"' for v in row) + "}" for row in rows
    )
    header = ", ".join(f'"{name}", STRING' for name, _ in col_defs)
    dax = (
        "DATATABLE(\n"
        f"\t\t\t\t{header},\n"
        "\t\t\t\t{\n"
        f"\t\t\t\t{row_strs}\n"
        "\t\t\t\t}\n"
        "\t\t\t)"
    )
    out.append(
        f"\tpartition {table_name} = calculated\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        f"\t\t\t{dax}\n"
    )
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def build_kpi_dictionary_table_tmdl() -> str:
    cols = [("KpiName", "string"), ("Formula", "string"), ("DataSource", "string"), ("UpdateFrequency", "string"), ("Owner", "string")]
    return _datatable_tmdl("KpiDictionary", cols, KPI_DICTIONARY)


def build_faq_table_tmdl() -> str:
    cols = [("Question", "string"), ("Answer", "string")]
    return _datatable_tmdl("FaqReference", cols, FAQ_ENTRIES)


def build_measures_table_tmdl() -> str:
    out = [f"table _Measures", f"\tlineageTag: {g()}", ""]
    for name, dax, fmt in MEASURES:
        out.append(measure_block(name, dax, fmt))
    out.append(
        "\tcolumn Value\n"
        "\t\tdataType: int64\n"
        f"\t\tlineageTag: {g()}\n"
        "\t\tisHidden\n"
        "\t\tsummarizeBy: none\n"
        "\t\tsourceColumn: Value\n"
        "\n"
        "\t\tannotation SummarizationSetBy = Automatic\n"
    )
    out.append(
        "\tpartition _Measures = calculated\n"
        "\t\tmode: import\n"
        '\t\tsource = ROW("Value", 1)\n'
    )
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def build_relationships_tmdl() -> str:
    rels = [
        ("fact_transactions.user_id", "dim_customers.user_id", True),
        ("fact_transactions.merchant_id", "dim_merchants.merchant_id", True),
        ("fact_chargebacks.user_id", "dim_customers.user_id", True),
        ("fact_chargebacks.merchant_id", "dim_merchants.merchant_id", True),
        ("fact_chargebacks.txn_id", "fact_transactions.txn_id", False),
        ("fact_transactions.TxnDate", "DateTable.Date", True),
        ("fact_chargebacks.ReportedDate", "DateTable.Date", True),
    ]
    out = []
    for from_col, to_col, active in rels:
        out.append(f"relationship {g()}")
        if not active:
            out.append("\tisActive: false")
        out.append(f"\tfromColumn: {from_col}")
        out.append(f"\ttoColumn: {to_col}")
        out.append("")
    return "\n".join(out)


def build_expressions_tmdl() -> str:
    escaped = WIN_DATA_FOLDER.replace('"', '""')
    return (
        f'expression DataFolder = "{escaped}" meta [IsParameterQuery=true, Type="Text", '
        f'IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {g()}\n"
        "\tannotation PBI_ResultType = Text\n"
    )


def build_model_tmdl() -> str:
    table_names = [t[0] for t in TABLES] + ["DateTable", "MerchantSpikeDays", "KpiDictionary", "FaqReference", "_Measures"]
    refs = "\n".join(f"ref table {t}" for t in table_names)
    return f"""model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 0

{refs}

ref expression DataFolder
"""


# ---------------------------------------------------------------------------
# Report generation (classic single-file report.json layout format)
# ---------------------------------------------------------------------------

def field(entity, name, kind):
    return {"entity": entity, "name": name, "kind": kind}


def measure(entity, name):
    return field(entity, name, "measure")


def column(entity, name):
    return field(entity, name, "column")


def build_visual_config(visual_type, roles, vid, title=None, extra_objects=None, risk=False):
    alias_map = {}
    entities = []
    select = []
    projections = {}

    def get_alias(entity):
        if entity not in alias_map:
            alias = chr(ord("a") + len(alias_map))
            alias_map[entity] = alias
            entities.append({"Name": alias, "Entity": entity, "Type": 0})
        return alias_map[entity]

    for role, fields in roles.items():
        proj_list = []
        for f in fields:
            alias = get_alias(f["entity"])
            qref = f'{f["entity"]}.{f["name"]}'
            if f["kind"] == "measure":
                select.append(
                    {
                        "Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": f["name"]},
                        "Name": qref,
                    }
                )
            else:
                select.append(
                    {
                        "Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": f["name"]},
                        "Name": qref,
                    }
                )
            proj_list.append({"queryRef": qref})
        projections[role] = proj_list

    objects = {}
    if title:
        objects["title"] = [
            {
                "properties": {
                    "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                }
            }
        ]
    # Every chart with axes gets its axis titles, tick labels, and scale
    # turned on explicitly -- Power BI's default is title-off, ticks-on,
    # which reads as unlabeled without this.
    if visual_type in ("lineChart", "clusteredColumnChart", "clusteredBarChart"):
        axis_block = [
            {
                "properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "showAxisTitle": {"expr": {"Literal": {"Value": "true"}}},
                }
            }
        ]
        objects["categoryAxis"] = axis_block
        objects["valueAxis"] = axis_block
    if extra_objects:
        objects.update(extra_objects)

    single_visual = {
        "visualType": visual_type,
        "projections": projections,
        "prototypeQuery": {"Version": 2, "From": entities, "Select": select},
        "drillFilterOtherVisuals": True,
        "objects": objects,
        "vcObjects": RISK_VC_OBJECTS if risk else CARD_VC_OBJECTS,
    }
    return {"name": vid, "layouts": [{"id": 0, "position": {}}], "singleVisual": single_visual}


def visual_container(x, y, w, h, visual_type, roles, title=None, extra_objects=None, risk=False):
    vid = g()
    cfg = build_visual_config(visual_type, roles, vid, title, extra_objects=extra_objects, risk=risk)
    cfg["layouts"][0]["position"] = {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
    }


SHOW_ALL_POINTS = {"dataPoint": [{"properties": {"showAllDataPoints": {"expr": {"Literal": {"Value": "true"}}}}}]}

# "Button-style" slicer items: rounded, filled chips that swap to the accent
# color on selection -- Power BI's own selection-highlight behavior is what
# supplies the "animation" (an instant, native color/press transition on
# click), this just gives it a pill/button shape to transition between.
SLICER_BUTTON_OBJECTS = {
    "items": [
        {
            "properties": {
                "background": {"solid": {"color": {"expr": {"Literal": {"Value": "'#F1F5F9'"}}}}},
                "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#334155'"}}}}},
                "outline": {"expr": {"Literal": {"Value": "'Frame'"}}},
                "outlineColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#E2E8F0'"}}}}},
                "outlineWeight": {"expr": {"Literal": {"Value": "1D"}}},
                "borderStyle": {"expr": {"Literal": {"Value": "'Rounded'"}}},
            }
        }
    ],
    "selection": [
        {
            "properties": {
                "selectAllCheckboxEnabled": {"expr": {"Literal": {"Value": "false"}}},
                "singleSelect": {"expr": {"Literal": {"Value": "false"}}},
            }
        }
    ],
}


def slicer(x, y, w, h, fld, title=None):
    return visual_container(x, y, w, h, "slicer", {"Values": [fld]}, title, extra_objects=SLICER_BUTTON_OBJECTS)


def build_section(display_name, ordinal, visuals):
    return {
        "name": f"Section{ordinal}",
        "displayName": display_name,
        "displayOption": 1,
        "filters": "[]",
        "height": 780,
        "width": 1280,
        "ordinal": ordinal,
        "visualContainers": visuals,
    }


# Layout constants: a horizontal page-navigator bar across the top of every
# page, then a left filter rail (mirrors the reference dashboard's
# left-column pattern), then the main content area. The old design used a
# hand-built column of actionButton icons down the left edge -- replaced
# with Power BI's own native "Page Navigator" visual (Insert > Buttons >
# Navigator > Page Navigator) so page-to-page clicking is handled by the
# report engine itself instead of hand-authored visualLink JSON.
RAIL_X, RAIL_W = 20, 200
MAIN_X, MAIN_W = 240, 1020

# One gap size for every seam in the report -- box-to-box horizontally
# (cards in a row, charts side by side) and row-to-row vertically. Card
# widths are *derived* from this so N cards always tile MAIN_W exactly,
# instead of a hand-picked width that only happened to fit one N.
GAP = 20
CARD_GAP = GAP
CARD_W = (MAIN_W - 3 * CARD_GAP) // 4
CARD_XS = [MAIN_X + i * (CARD_W + CARD_GAP) for i in range(4)]
CARD3_W = (MAIN_W - 2 * CARD_GAP) // 3
CARD3_XS = [MAIN_X + i * (CARD3_W + CARD_GAP) for i in range(3)]

# Top header row occupies y=10..60; a further 20px gap puts every page's
# first content row at a fixed y=80. The row holds a plain-text report title
# on the left and the page navigator filling the rest, mirroring the
# reference dashboard's single "logo + title | controls" header band instead
# of stacking them as two separate rows.
TOP_NAV_Y, TOP_NAV_H = 10, 50
CONTENT_Y = TOP_NAV_Y + TOP_NAV_H + GAP  # 80

PAGE_TITLE = "UPI Transaction Anomaly & Risk Intelligence"
TITLE_W = 480


def page_title(x, y, w, h, text, font_size="20D", align="Left"):
    # A borderless, background-less actionButton used purely as a styled
    # text label (no visualLink -- not clickable) -- the same low-risk
    # "text" object already proven safe for the nav icons earlier in this
    # project, reused here instead of hand-authoring the textbox visual's
    # less-familiar paragraph/textRun schema.
    vid = g()
    single_visual = {
        "visualType": "actionButton",
        "drillFilterOtherVisuals": False,
        "objects": {
            "text": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{text}'"}}},
                "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#111111'"}}}}},
                "fontSize": {"expr": {"Literal": {"Value": font_size}}},
                "horizontalAlignment": {"expr": {"Literal": {"Value": f"'{align}'"}}},
                "verticalAlignment": {"expr": {"Literal": {"Value": "'Middle'"}}},
            }}],
            "fill": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
            "outline": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
        },
        "vcObjects": {},
    }
    return {
        "x": x, "y": y, "z": 0, "width": w, "height": h,
        "config": json.dumps({
            "name": vid,
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}}],
            "singleVisual": single_visual,
        }),
    }


def link_button(x, y, w, h, text, url, bg="'#2FB6B0'", fg="'#FFFFFF'"):
    # actionButton with a "Web URL" action -- same visualLink object family
    # already verified (via the earlier PageNavigation buttons) to load
    # without a schema error; only the action "type" and target property
    # name change for an external link instead of an in-report page.
    vid = g()
    single_visual = {
        "visualType": "actionButton",
        "drillFilterOtherVisuals": False,
        "objects": {
            "text": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{text}'"}}},
                "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": fg}}}}},
                "fontSize": {"expr": {"Literal": {"Value": "14D"}}},
                "horizontalAlignment": {"expr": {"Literal": {"Value": "'Center'"}}},
                "verticalAlignment": {"expr": {"Literal": {"Value": "'Middle'"}}},
            }}],
            "fill": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "fillColor": {"solid": {"color": {"expr": {"Literal": {"Value": bg}}}}},
                "transparency": {"expr": {"Literal": {"Value": "0D"}}},
            }}],
            "outline": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "weight": {"expr": {"Literal": {"Value": "0D"}}},
                "radius": {"expr": {"Literal": {"Value": "10D"}}},
            }}],
            "visualLink": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "type": {"expr": {"Literal": {"Value": "'WebURL'"}}},
                "webUrl": {"expr": {"Literal": {"Value": f"'{url}'"}}},
            }}],
        },
        "vcObjects": {},
    }
    return {
        "x": x, "y": y, "z": 0, "width": w, "height": h,
        "config": json.dumps({
            "name": vid,
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}}],
            "singleVisual": single_visual,
        }),
    }


def page_navigator(x=None, y=None, w=None, h=None):
    vid = g()
    x = RAIL_X if x is None else x
    y = TOP_NAV_Y if y is None else y
    w = (MAIN_X + MAIN_W - RAIL_X) if w is None else w
    h = TOP_NAV_H if h is None else h
    single_visual = {
        "visualType": "pageNavigator",
        "drillFilterOtherVisuals": True,
        # Deliberately no custom "objects" here: the Page/Bookmark Navigator
        # family uses its own non-standard style-card schema that isn't
        # reliably documented, so we only theme the outer container (safe,
        # generic vcObjects) and leave the navigator's own button styling at
        # Power BI's default rather than risk a malformed style object.
        "vcObjects": CARD_VC_OBJECTS,
    }
    return {
        "x": x, "y": y, "z": 0, "width": w, "height": h,
        "config": json.dumps({
            "name": vid,
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}}],
            "singleVisual": single_visual,
        }),
    }


def page_header():
    nav_x = RAIL_X + TITLE_W + GAP
    return [
        page_title(RAIL_X, TOP_NAV_Y, TITLE_W, TOP_NAV_H, PAGE_TITLE),
        page_navigator(x=nav_x, w=(MAIN_X + MAIN_W) - nav_x),
    ]


def rail(fields_titles):
    # fields_titles: list of (field, title). Stacks slicers down the left rail.
    n = len(fields_titles)
    h = (680 - (n - 1) * 20) // n
    out = []
    y = CONTENT_Y
    for fld, title in fields_titles:
        out.append(slicer(RAIL_X, y, RAIL_W, h, fld, title))
        y += h + 20
    return out


def build_pages():
    m = lambda n: measure("_Measures", n)
    c = lambda t, n: column(t, n)

    page1_rail = rail(
        [
            (c("DateTable", "Date"), "Date"),
            (c("dim_merchants", "MerchantCategoryDisplay"), "Merchant Category"),
            (c("fact_transactions", "StatusDisplay"), "Transaction Status"),
            (c("fact_transactions", "UTRProblem"), "UTR Problem? (one-click)"),
        ]
    )
    # Vertical rhythm matches pages 2 and 3 exactly: row1 at y=80 (h=90),
    # +20 gap, row2 at y=190 (h=260), +20 gap, row3 at y=470 (h=290),
    # ending at y=760 with the same 20px bottom margin as every other page.
    page1 = page_header() + page1_rail + [
        visual_container(CARD_XS[0], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Total Transactions")]}, "Total Transactions"),
        visual_container(CARD_XS[1], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Total Txn Amount")]}, "Total Txn Amount"),
        visual_container(CARD_XS[2], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Success Rate")]}, "Success Rate"),
        visual_container(CARD_XS[3], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Chargeback Count")]}, "Chargeback Count", risk=True),
        visual_container(MAIN_X, 190, 500, 260, "lineChart", {"Category": [c("DateTable", "Date")], "Y": [m("Total Transactions")]}, "Daily Transaction Count"),
        visual_container(MAIN_X + 520, 190, 500, 260, "lineChart", {"Category": [c("DateTable", "Date")], "Y": [m("Total Txn Amount")]}, "Daily Transaction Value"),
        visual_container(
            MAIN_X, 470, MAIN_W, 290, "clusteredColumnChart",
            {"Category": [c("dim_merchants", "MerchantCategoryDisplay"), c("dim_merchants", "MerchantNameDisplay")], "Y": [m("Total Txn Amount")]},
            "Transaction Amount by Merchant Category (click a bar, or right-click > Drill Down to Merchant Name)",
            extra_objects=SHOW_ALL_POINTS,
        ),
    ]

    page2_rail = rail(
        [
            (c("fact_chargebacks", "DelayBucket"), "Reporting Delay Bucket (one-click)"),
            (c("fact_chargebacks", "timestamps_logically_valid"), "Timestamps Logically Valid"),
            (c("fact_chargebacks", "resolution_status"), "Resolution Status"),
            (c("fact_chargebacks", "channel"), "Channel"),
        ]
    )
    page2 = page_header() + page2_rail + [
        visual_container(CARD_XS[0], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Chargeback Amount")]}, "Chargeback Amount", risk=True),
        visual_container(CARD_XS[1], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("CB to Txn Ratio (Count)")]}, "CB to Txn Ratio", risk=True),
        visual_container(CARD_XS[2], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Avg Dispute Delay (Days)")]}, "Avg Dispute Delay (Days)", risk=True),
        visual_container(CARD_XS[3], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Disputes Reported After 7d")]}, "Disputes After 7d", risk=True),
        visual_container(MAIN_X, 190, 330, 260, "donutChart", {"Category": [c("fact_chargebacks", "reason_code")], "Y": [m("Chargeback Count")]}, "Chargeback Reason Distribution"),
        visual_container(MAIN_X + 350, 190, 330, 260, "donutChart", {"Category": [c("fact_chargebacks", "severity")], "Y": [m("Chargeback Count")]}, "Chargeback Severity Distribution"),
        visual_container(
            MAIN_X + 700, 190, 320, 260, "clusteredBarChart",
            {"Category": [c("dim_merchants", "MerchantCategoryDisplay")], "Y": [m("Merchant CB to Txn Ratio")]},
            "Merchant CB-to-Txn Ratio by Category", extra_objects=SHOW_ALL_POINTS,
        ),
        visual_container(MAIN_X, 470, MAIN_W, 290, "tableEx", {"Values": [c("dim_merchants", "MerchantNameDisplay"), m("Chargeback Count"), m("Chargeback Amount")]}, "Top Merchants by Chargeback Exposure"),
    ]

    page3_rail = rail(
        [
            (c("dim_customers", "KycStatusDisplay"), "KYC Status"),
            (c("dim_customers", "RiskSegmentDisplay"), "Risk Segment"),
            (c("dim_customers", "DisputeRiskFlag"), "Customer Dispute Risk (one-click)"),
            (c("dim_merchants", "HadSpikeDay"), "Merchant Spike Day (one-click)"),
        ]
    )
    page3 = page_header() + page3_rail + [
        visual_container(CARD_XS[0], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("KYC Completion Rate")]}, "KYC Completion Rate"),
        visual_container(CARD_XS[1], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("KYC Rejection Rate")]}, "KYC Rejection Rate"),
        visual_container(CARD_XS[2], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Txn User FK Match Rate")]}, "Txn-KYC Match Rate"),
        visual_container(CARD_XS[3], CONTENT_Y, CARD_W, 90, "card", {"Values": [m("Txn Merchant FK Match Rate")]}, "Txn-Merchant Match Rate"),
        visual_container(MAIN_X, 190, 500, 260, "donutChart", {"Category": [c("dim_customers", "KycStatusDisplay")], "Y": [m("Total Customers")]}, "KYC Status Distribution"),
        visual_container(
            MAIN_X + 520, 190, 500, 260, "clusteredBarChart",
            {"Category": [c("dim_customers", "StateDisplay"), c("dim_customers", "CityDisplay")], "Y": [m("Total Transactions")]},
            "Transactions by Customer State (right-click > Drill Down to City)",
            extra_objects=SHOW_ALL_POINTS,
        ),
        visual_container(MAIN_X, 470, MAIN_W, 290, "tableEx", {"Values": [c("fact_chargebacks", "user_id"), m("Chargeback Count"), m("Chargeback Amount")]}, "Users by Chargeback Count (sort by Chargeback Count to see repeat-dispute users)"),
    ]

    page4_rail = rail(
        [
            (c("dim_merchants", "MerchantCategoryDisplay"), "Merchant Category"),
            (c("dim_merchants", "MerchantStatusDisplay"), "Merchant Status"),
            (c("dim_merchants", "DisputeRiskFlag"), "Merchant Dispute Risk (one-click)"),
            (c("dim_merchants", "HadSpikeDay"), "Merchant Spike Day (one-click)"),
        ]
    )
    page4 = page_header() + page4_rail + [
        visual_container(CARD3_XS[0], CONTENT_Y, CARD3_W, 90, "card", {"Values": [m("Pending Rate")]}, "Pending Rate"),
        visual_container(CARD3_XS[1], CONTENT_Y, CARD3_W, 90, "card", {"Values": [m("Failed Rate")]}, "Failed Rate"),
        visual_container(CARD3_XS[2], CONTENT_Y, CARD3_W, 90, "card", {"Values": [m("Avg Txn Value")]}, "Avg Txn Value"),
        visual_container(CARD3_XS[0], 190, CARD3_W, 90, "card", {"Values": [m("Transactions Missing/Invalid UTR Rate")]}, "Missing/Invalid UTR Rate", risk=True),
        visual_container(CARD3_XS[1], 190, CARD3_W, 90, "card", {"Values": [m("High Risk Merchants (2+ Disputes)")]}, "High Risk Merchants (2+ Disputes)", risk=True),
        visual_container(CARD3_XS[2], 190, CARD3_W, 90, "card", {"Values": [m("Merchant-Day Spikes (2+ Txns)")]}, "Merchant-Day Spikes (2+ Txns)", risk=True),
        visual_container(
            MAIN_X, 300, 500, 460, "tableEx",
            {"Values": [c("dim_merchants", "MerchantNameDisplay"), c("dim_merchants", "MerchantCategoryDisplay"), m("Chargeback Count"), m("Chargeback Amount")]},
            "Top Merchants by Disputed Amount (sort by Chargeback Amount)",
        ),
        visual_container(
            MAIN_X + 520, 300, 500, 460, "tableEx",
            {"Values": [column("MerchantSpikeDays", "MerchantName"), column("MerchantSpikeDays", "MerchantCategory"), column("MerchantSpikeDays", "TxnDate"), column("MerchantSpikeDays", "TxnCount")]},
            "Merchant Same-Day Transaction Spikes (2+ txns/day -- suspicious clusters)",
        ),
    ]

    # KPI Reference page: FAQ list (left, narrower -- it's prose, not a
    # table) + the KPI Dictionary (right, wide -- 5 columns need the room) on
    # top, and a chatbot callout spanning the full width along the bottom.
    # RAIL_X..bottom margin math matches every other page (CONTENT_Y=80,
    # bottom=760, 20px gaps throughout).
    faq_w = 340
    dict_x = RAIL_X + faq_w + GAP
    dict_w = (MAIN_X + MAIN_W) - dict_x
    upper_h = 510
    footer_y = CONTENT_Y + upper_h + GAP  # 610
    footer_h = 150  # ends at 760, matching every other page's bottom margin

    page5 = page_header() + [
        visual_container(
            RAIL_X, CONTENT_Y, faq_w, upper_h, "multiRowCard",
            {"Values": [column("FaqReference", "Question"), column("FaqReference", "Answer")]},
            "Frequently Asked Questions",
        ),
        visual_container(
            dict_x, CONTENT_Y, dict_w, upper_h, "tableEx",
            {"Values": [
                column("KpiDictionary", "KpiName"), column("KpiDictionary", "Formula"),
                column("KpiDictionary", "DataSource"), column("KpiDictionary", "UpdateFrequency"),
                column("KpiDictionary", "Owner"),
            ]},
            "KPI Dictionary -- formula, source, refresh cadence, and owner for every number on this report",
        ),
        page_title(
            RAIL_X, footer_y, 760, footer_h,
            "Want a number explained in plain English? Open the live chatbot -- it answers from the exact same "
            "cleaned dataset as every chart on this report, and shows the SQL behind each answer.",
            font_size="15D",
        ),
        link_button(RAIL_X + 760 + GAP, footer_y + (footer_h - 50) // 2, 240, 50, "\U0001F4AC Open Live Chatbot ↗", "http://129.159.234.80/"),
    ]

    return [
        build_section("Overview", 0, page1),
        build_section("Fraud & Dispute Analysis", 1, page2),
        build_section("Customer Risk & Data Quality", 2, page3),
        build_section("Fraud-Ring Spotlight", 3, page4),
        build_section("KPI Reference", 4, page5),
    ]


THEME_NAME = "UPIFraudTheme"

# Color code matched to the reference dashboard (metricalist.com HR report
# template) screenshot: white surfaces, near-black text/headline accents,
# teal as the primary data color, a violet secondary, and neutral grays for
# de-emphasized categories -- the same "one bold neutral + one bright accent"
# formula that template uses for its KPI cards, donut, and bar charts.
# "bad"/risk stays crimson rather than following that formula, since this
# report (unlike the HR reference) has a real danger/fraud signal that needs
# to read as an alert regardless of the rest of the palette.
THEME = {
    "name": THEME_NAME,
    "dataColors": ["#2FB6B0", "#111111", "#6C4FA6", "#8C8C8C", "#57D6CE", "#3D3D3D", "#9A87CE", "#C9C9C9"],
    "background": "#FFFFFF",
    "foreground": "#111111",
    "tableAccent": "#111111",
    "good": "#2FB6B0",
    "neutral": "#8C8C8C",
    "bad": "#9D174D",
}

# Soft drop shadow applied to every visual container -- standard Power BI
# "Effects > Shadow" formatting object, not a custom visual, so it's a
# low-risk, best-effort formatting property (silently ignored if some field
# doesn't apply, never a load-time schema error).
SOFT_SHADOW = [
    {
        "properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#0F172A'"}}}}},
            "transparency": {"expr": {"Literal": {"Value": "88D"}}},
            "position": {"expr": {"Literal": {"Value": "'Outside'"}}},
            "shadowBlur": {"expr": {"Literal": {"Value": "14D"}}},
            "shadowDistance": {"expr": {"Literal": {"Value": "4D"}}},
            "shadowSpread": {"expr": {"Literal": {"Value": "0D"}}},
            "direction": {"expr": {"Literal": {"Value": "90D"}}},
        }
    }
]

# Rounded-corner, thin-bordered "card" look for every visual container --
# clean white surface, a neutral light-gray hairline border (matches the
# reference dashboard's minimal card style).
CARD_VC_OBJECTS = {
    "background": [
        {"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#FFFFFF'"}}}}}, "transparency": {"expr": {"Literal": {"Value": "0D"}}}}}
    ],
    "border": [
        {"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#E3E3E3'"}}}}}, "radius": {"expr": {"Literal": {"Value": "12D"}}}, "width": {"expr": {"Literal": {"Value": "1D"}}}}}
    ],
    "dropShadow": SOFT_SHADOW,
}

# "Risk elevation" variant for cards surfacing active fraud/dispute exposure
# (spec: a subtle colored glow on cards showing active fraud or anomalous
# spikes). A literal crimson border + light-red tint, not a dynamic
# conditional-formatting rule -- these specific cards (Chargeback Count, the
# whole Fraud & Dispute page's headline row) are inherently risk-signal cards
# regardless of the current value, so a static style is the honest choice;
# value-conditional coloring would need a FillRule expression, which is
# higher-risk to hand-author than a literal color (see relationship-endpoint
# note above for why "higher-risk hand-authored JSON" is worth avoiding here).
RISK_VC_OBJECTS = {
    "background": [
        {"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#FDF2F8'"}}}}}, "transparency": {"expr": {"Literal": {"Value": "0D"}}}}}
    ],
    "border": [
        {"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#9D174D'"}}}}}, "radius": {"expr": {"Literal": {"Value": "12D"}}}, "width": {"expr": {"Literal": {"Value": "1D"}}}}}
    ],
    "dropShadow": SOFT_SHADOW,
}


# dim_customers and dim_merchants each get one Power-BI-inserted "unknown
# member" row for fact rows whose foreign key doesn't match any real
# customer/merchant (28920 vs 28921 rows, 4343 vs 4344 -- confirmed via live
# DAX earlier). It shows up as a bare "(Blank)" entry in every slicer/chart/
# table built from that table's own columns. DAX calculated columns never
# evaluate for that synthetic row, so no IF(ISBLANK(...),...) guard can
# relabel it -- the only way to remove it from display is a filter that
# excludes it outright. One report-level "primary key is not blank" filter
# per table removes that row from every visual on every page in one shot,
# instead of adding the same filter by hand to a dozen+ individual visuals.
def not_blank_report_filter(table, column):
    return {
        "name": g(),
        "expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}},
        "filterType": 1,
        "howCreated": 1,
        "type": "Advanced",
        "conditions": [{"operator": "IsNotBlank"}],
    }


REPORT_FILTERS = [
    not_blank_report_filter("dim_customers", "user_id"),
    not_blank_report_filter("dim_merchants", "merchant_id"),
]


def build_report_json():
    return {
        "id": 0,
        "resourcePackages": [
            {
                "resourcePackage": {
                    "name": "SharedResources",
                    "type": 2,
                    "items": [{"type": 202, "path": f"BaseThemes/{THEME_NAME}.json", "name": THEME_NAME}],
                }
            }
        ],
        "config": json.dumps({"version": "5.55", "themeCollection": {"baseTheme": {"name": THEME_NAME}}, "activeSectionIndex": 0}),
        "layoutOptimization": 0,
        "publicCustomVisuals": [],
        "filters": json.dumps(REPORT_FILTERS),
        "sections": build_pages(),
        "sectionGroups": [],
    }


# ---------------------------------------------------------------------------
# Project scaffolding (.pbip / .platform / .pbism / .pbir)
# ---------------------------------------------------------------------------

def build_semantic_model():
    write(MODEL_DIR / "definition" / "model.tmdl", build_model_tmdl())
    write(MODEL_DIR / "definition" / "relationships.tmdl", build_relationships_tmdl())
    write(MODEL_DIR / "definition" / "expressions.tmdl", build_expressions_tmdl())
    for name, cols in TABLES:
        write(MODEL_DIR / "definition" / "tables" / f"{name}.tmdl", build_table_tmdl(name, cols))
    write(MODEL_DIR / "definition" / "tables" / "DateTable.tmdl", build_date_table_tmdl())
    write(MODEL_DIR / "definition" / "tables" / "MerchantSpikeDays.tmdl", build_merchant_spike_table_tmdl())
    write(MODEL_DIR / "definition" / "tables" / "KpiDictionary.tmdl", build_kpi_dictionary_table_tmdl())
    write(MODEL_DIR / "definition" / "tables" / "FaqReference.tmdl", build_faq_table_tmdl())
    write(MODEL_DIR / "definition" / "tables" / "_Measures.tmdl", build_measures_table_tmdl())

    write_json(
        MODEL_DIR / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": PROJECT},
            "config": {"version": "2.0", "logicalId": g()},
        },
    )
    write_json(MODEL_DIR / "definition.pbism", {"version": "4.2", "settings": {}})


def build_report():
    write_json(REPORT_DIR / "report.json", build_report_json())
    write_json(REPORT_DIR / "StaticResources" / "SharedResources" / "BaseThemes" / f"{THEME_NAME}.json", THEME)
    write_json(
        REPORT_DIR / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": PROJECT},
            "config": {"version": "2.0", "logicalId": g()},
        },
    )
    write_json(
        REPORT_DIR / "definition.pbir",
        {"version": "1.0", "datasetReference": {"byPath": {"path": f"../{PROJECT}.SemanticModel"}}},
    )


def build_pbip():
    write_json(
        PBI_DIR / f"{PROJECT}.pbip",
        {
            "version": "1.0",
            "artifacts": [{"report": {"path": f"{PROJECT}.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )


def main():
    build_semantic_model()
    build_report()
    build_pbip()
    print(f"Wrote Power BI project to {PBI_DIR}")
    print(f"Open: {PBI_DIR / (PROJECT + '.pbip')}")


if __name__ == "__main__":
    main()
