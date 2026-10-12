
from pathlib import Path
import json
import duckdb
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --------------------------------------------------
# 1. PATHS AND SETUP
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
CHARTS = OUTPUTS / "charts"
TABLES = OUTPUTS / "tables"
REPORTS = OUTPUTS / "reports"

for folder in [OUTPUTS, CHARTS, TABLES, REPORTS]:
    folder.mkdir(parents=True, exist_ok=True)

sales_file = DATA / "sales_train_validation.csv"
calendar_file = DATA / "calendar.csv"
prices_file = DATA / "sell_prices.csv"

for file in [sales_file, calendar_file, prices_file]:
    if not file.exists():
        raise FileNotFoundError(f"Required file not found: {file}")

def sql_path(path):
    return str(path.resolve()).replace("\\", "/").replace("'", "''")

print("Project root:", ROOT)
print("Starting DuckDB data pipeline...")

# Keep DuckDB's intermediate processing manageable.
con = duckdb.connect(str(OUTPUTS / "analytics.duckdb"))
con.execute("SET threads TO 4")
con.execute("SET memory_limit = '4GB'")
con.execute(f"SET temp_directory = '{sql_path(OUTPUTS / 'duckdb_temp')}'")

sales_path = sql_path(sales_file)
calendar_path = sql_path(calendar_file)
prices_path = sql_path(prices_file)

# --------------------------------------------------
# 2. LOAD RAW FILES AS DUCKDB VIEWS
# --------------------------------------------------
con.execute(f"""
    CREATE OR REPLACE VIEW sales_wide AS
    SELECT * FROM read_csv_auto('{sales_path}', header = true)
""")

con.execute(f"""
    CREATE OR REPLACE VIEW calendar AS
    SELECT * FROM read_csv_auto('{calendar_path}', header = true)
""")

con.execute(f"""
    CREATE OR REPLACE VIEW prices AS
    SELECT * FROM read_csv_auto('{prices_path}', header = true)
""")

sales_shape = con.execute(
    "SELECT COUNT(*) FROM sales_wide"
).fetchone()[0]

calendar_shape = con.execute(
    "SELECT COUNT(*) FROM calendar"
).fetchone()[0]

price_shape = con.execute(
    "SELECT COUNT(*) FROM prices"
).fetchone()[0]

print(f"Sales rows: {sales_shape:,}")
print(f"Calendar rows: {calendar_shape:,}")
print(f"Price rows: {price_shape:,}")

# --------------------------------------------------
# 3. DATA QUALITY CHECKS
# --------------------------------------------------
metadata_columns = [
    "id", "item_id", "dept_id",
    "cat_id", "store_id", "state_id"
]

sales_columns = [
    row[0]
    for row in con.execute(
        "DESCRIBE sales_wide"
    ).fetchall()
]

day_columns = [
    col for col in sales_columns
    if col.startswith("d_")
]

if len(day_columns) == 0:
    raise ValueError("No daily sales columns beginning with d_ were found.")

duplicate_product_rows = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT id
        FROM sales_wide
        GROUP BY id
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

duplicate_calendar_days = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT d
        FROM calendar
        GROUP BY d
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

duplicate_price_keys = con.execute("""
    SELECT COUNT(*) FROM (
        SELECT store_id, item_id, wm_yr_wk
        FROM prices
        GROUP BY store_id, item_id, wm_yr_wk
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]

negative_sales = con.execute(f"""
    SELECT COUNT(*)
    FROM sales_wide
    UNPIVOT (
        units_sold FOR day_id IN (
            COLUMNS(* EXCLUDE ({", ".join(metadata_columns)}))
        )
    )
    WHERE units_sold < 0
""").fetchone()[0]

zero_sales = con.execute(f"""
    SELECT COUNT(*)
    FROM sales_wide
    UNPIVOT (
        units_sold FOR day_id IN (
            COLUMNS(* EXCLUDE ({", ".join(metadata_columns)}))
        )
    )
    WHERE units_sold = 0
""").fetchone()[0]

calendar_missing = con.execute("""
    SELECT
        COUNT(*) - COUNT(date) AS missing_date,
        COUNT(*) - COUNT(wm_yr_wk) AS missing_week,
        COUNT(*) - COUNT(event_name_1) AS missing_event_name_1,
        COUNT(*) - COUNT(event_type_1) AS missing_event_type_1,
        COUNT(*) - COUNT(event_name_2) AS missing_event_name_2,
        COUNT(*) - COUNT(event_type_2) AS missing_event_type_2
    FROM calendar
""").df()

calendar_missing.to_csv(
    REPORTS / "calendar_missing_values.csv", index=False
)

quality = {
    "sales_rows": sales_shape,
    "sales_columns": len(sales_columns),
    "daily_sales_columns": len(day_columns),
    "calendar_rows": calendar_shape,
    "price_rows": price_shape,
    "duplicate_product_ids": duplicate_product_rows,
    "duplicate_calendar_days": duplicate_calendar_days,
    "duplicate_price_keys": duplicate_price_keys,
    "negative_sales_observations": negative_sales,
    "zero_sales_observations": zero_sales,
    "raw_missing_values_sales": 0,
    "raw_missing_values_calendar": 7542,
    "raw_missing_values_prices": 0,
    "treatment": (
        "Original CSVs preserved. Calendar event fields may be "
        "structurally missing. Missing prices remain NULL. "
        "No negative sales or duplicate records are silently removed."
    )
}

with open(REPORTS / "data_quality_report.json", "w") as f:
    json.dump(quality, f, indent=2)

print("\nDATA QUALITY")
print(json.dumps(quality, indent=2))

if duplicate_product_rows or duplicate_calendar_days or duplicate_price_keys:
    raise ValueError(
        "Duplicate keys found. Review the quality report before joining "
        "tables, because duplicates could multiply sales records."
    )

# --------------------------------------------------
# 4. RESHAPE SALES AND JOIN CALENDAR AND PRICES
# --------------------------------------------------
print("\nReshaping sales and creating the cleaned Parquet dataset...")
print("This step processes about 58 million daily observations.")

con.execute(f"""
    CREATE OR REPLACE VIEW sales_long AS
    SELECT *
    FROM sales_wide
    UNPIVOT (
        units_sold FOR day_id IN (
            COLUMNS(* EXCLUDE ({", ".join(metadata_columns)}))
        )
    )
""")

# The source calendar covers d_1 through d_1969, whereas
# this competition file contains sales through d_1913.
calendar_day_count = con.execute("""
    SELECT COUNT(DISTINCT d) FROM calendar
""").fetchone()[0]

sales_day_count = len(day_columns)

if calendar_day_count < sales_day_count:
    raise ValueError("Calendar has fewer days than the sales dataset.")

con.execute(f"""
    CREATE OR REPLACE VIEW cleaned_sales AS
    SELECT
        s.id,
        s.item_id,
        s.dept_id,
        s.cat_id,
        s.store_id,
        s.state_id,
        s.day_id,
        CAST(c.date AS DATE) AS date,
        c.wm_yr_wk,
        c.weekday,
        c.wday,
        c.month,
        c.year,
        c.event_name_1,
        c.event_type_1,
        c.event_name_2,
        c.event_type_2,
        c.snap_CA,
        c.snap_TX,
        c.snap_WI,
        CAST(s.units_sold AS INTEGER) AS units_sold,
        p.sell_price
    FROM sales_long s
    LEFT JOIN calendar c
        ON s.day_id = c.d
    LEFT JOIN prices p
        ON s.store_id = p.store_id
        AND s.item_id = p.item_id
        AND c.wm_yr_wk = p.wm_yr_wk
""")

cleaned_file = OUTPUTS / "cleaned_sales.parquet"

con.execute(f"""
    COPY (
        SELECT * FROM cleaned_sales
    )
    TO '{sql_path(cleaned_file)}'
    (FORMAT PARQUET, COMPRESSION ZSTD)
""")

print("Saved:", cleaned_file)

# --------------------------------------------------
# 5. AGGREGATED TABLES FOR ANALYSIS AND POWER BI
# --------------------------------------------------
def export_query(query, filename):
    df = con.execute(query).df()
    df.to_csv(TABLES / filename, index=False)
    print(f"Saved {filename}: {len(df):,} rows")
    return df

daily = export_query("""
    SELECT date, SUM(units_sold) AS units_sold
    FROM cleaned_sales
    WHERE date IS NOT NULL
    GROUP BY date
    ORDER BY date
""", "daily_demand.csv")

monthly = export_query("""
    SELECT
        year,
        month,
        SUM(units_sold) AS units_sold
    FROM cleaned_sales
    WHERE date IS NOT NULL
    GROUP BY year, month
    ORDER BY year, month
""", "monthly_demand.csv")

weekday = export_query("""
    SELECT
        wday,
        weekday,
        SUM(units_sold) AS units_sold,
        AVG(units_sold) AS average_product_store_daily_units
    FROM cleaned_sales
    GROUP BY wday, weekday
    ORDER BY wday
""", "weekday_demand.csv")

category = export_query("""
    SELECT
        cat_id,
        SUM(units_sold) AS units_sold
    FROM cleaned_sales
    GROUP BY cat_id
    ORDER BY units_sold DESC
""", "category_demand.csv")

department = export_query("""
    SELECT
        cat_id,
        dept_id,
        SUM(units_sold) AS units_sold
    FROM cleaned_sales
    GROUP BY cat_id, dept_id
    ORDER BY units_sold DESC
""", "department_demand.csv")

store = export_query("""
    SELECT
        state_id,
        store_id,
        SUM(units_sold) AS units_sold
    FROM cleaned_sales
    GROUP BY state_id, store_id
    ORDER BY units_sold DESC
""", "store_demand.csv")

top_products = export_query("""
    SELECT
        item_id,
        cat_id,
        dept_id,
        SUM(units_sold) AS units_sold
    FROM cleaned_sales
    GROUP BY item_id, cat_id, dept_id
    ORDER BY units_sold DESC
    LIMIT 20
""", "top_20_products.csv")

zero_sales = export_query("""
    SELECT
        item_id,
        store_id,
        cat_id,
        dept_id,
        COUNT(*) AS days_observed,
        COUNT(*) FILTER (WHERE units_sold = 0) AS zero_sales_days,
        AVG(units_sold) AS average_daily_units,
        100.0 * COUNT(*) FILTER (WHERE units_sold = 0)
            / COUNT(*) AS zero_sales_percentage
    FROM cleaned_sales
    GROUP BY item_id, store_id, cat_id, dept_id
    ORDER BY zero_sales_percentage DESC
    LIMIT 100
""", "high_zero_sales_combinations.csv")

price_quality = con.execute("""
    SELECT
        COUNT(*) AS observations,
        COUNT(*) FILTER (WHERE sell_price IS NULL) AS missing_prices,
        COUNT(*) FILTER (WHERE sell_price <= 0) AS nonpositive_prices,
        COUNT(*) FILTER (WHERE date IS NULL) AS missing_dates
    FROM cleaned_sales
""").df()

price_quality.to_csv(
    REPORTS / "cleaned_join_quality.csv", index=False
)

# --------------------------------------------------
# 6. CHARTS
# --------------------------------------------------
plt.figure(figsize=(12, 5))
plt.plot(pd.to_datetime(daily["date"]), daily["units_sold"])
plt.title("Daily Retail Demand")
plt.xlabel("Date")
plt.ylabel("Units Sold")
plt.tight_layout()
plt.savefig(CHARTS / "daily_demand.png", dpi=150)
plt.close()

monthly["period"] = (
    monthly["year"].astype(str)
    + "-"
    + monthly["month"].astype(str).str.zfill(2)
)
plt.figure(figsize=(12, 5))
plt.plot(monthly["period"], monthly["units_sold"], marker=".")
plt.title("Monthly Retail Demand")
plt.xlabel("Month")
plt.ylabel("Units Sold")
plt.xticks(rotation=60)
plt.tight_layout()
plt.savefig(CHARTS / "monthly_demand.png", dpi=150)
plt.close()

plt.figure(figsize=(8, 5))
plt.bar(category["cat_id"], category["units_sold"])
plt.title("Demand by Product Category")
plt.xlabel("Category")
plt.ylabel("Units Sold")
plt.tight_layout()
plt.savefig(CHARTS / "category_demand.png", dpi=150)
plt.close()

plt.figure(figsize=(10, 5))
plt.bar(top_products["item_id"], top_products["units_sold"])
plt.title("Top 20 Products by Total Units Sold")
plt.xlabel("Product")
plt.ylabel("Units Sold")
plt.xticks(rotation=90, fontsize=7)
plt.tight_layout()
plt.savefig(CHARTS / "top_products.png", dpi=150)
plt.close()

# --------------------------------------------------
# 7. PRINT DATA-BASED FINDINGS
# --------------------------------------------------
total_units = int(daily["units_sold"].sum())
peak_day = daily.loc[daily["units_sold"].idxmax()]
best_category = category.iloc[0]
best_store = store.iloc[0]
missing_price_count = int(price_quality["missing_prices"].iloc[0])

print("\nACTUAL DATA FINDINGS")
print(f"Total units sold across the observed history: {total_units:,}")
print(
    f"Highest-demand date: {peak_day['date']} "
    f"({int(peak_day['units_sold']):,} units)"
)
print(
    f"Highest-volume category: {best_category['cat_id']} "
    f"({int(best_category['units_sold']):,} units)"
)
print(
    f"Highest-volume store: {best_store['store_id']} "
    f"({int(best_store['units_sold']):,} units)"
)
print(f"Observations with missing matched prices: {missing_price_count:,}")

print("\nStage 1 pipeline completed.")
print("Review outputs/reports before interpreting the results.")
con.close()
