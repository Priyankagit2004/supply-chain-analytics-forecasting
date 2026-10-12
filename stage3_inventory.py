
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
TABLES.mkdir(parents=True, exist_ok=True)

PARQUET = OUTPUTS / "cleaned_sales.parquet"

if not PARQUET.exists():
    raise FileNotFoundError(f"Missing dataset: {PARQUET}")

# Illustrative assumptions — not provided by the M5 dataset.
LEAD_TIME_DAYS = 7
REVIEW_PERIOD_DAYS = 7
SERVICE_LEVEL = 0.95
Z_SCORE = 1.645

con = duckdb.connect()
path = str(PARQUET.resolve()).replace("\\", "/").replace("'", "''")

# Reuse the product-store combination evaluated in Stage 2.
predictions_path = TABLES / "forecast_predictions.csv"

if not predictions_path.exists():
    raise FileNotFoundError(
        "Run stage2_forecasting.py before this script."
    )

# Read the selected product and store from the Stage 2 output's
# selected combination is recorded by querying the same rule.
selected = con.execute(f"""
    SELECT item_id, store_id
    FROM read_parquet('{path}')
    GROUP BY item_id, store_id
    ORDER BY SUM(units_sold) DESC
    LIMIT 1
""").df().iloc[0]

item_id = selected["item_id"]
store_id = selected["store_id"]

history = con.execute(f"""
    SELECT date, units_sold
    FROM read_parquet('{path}')
    WHERE item_id = '{item_id}'
      AND store_id = '{store_id}'
    ORDER BY date
""").df()

con.close()

history["date"] = pd.to_datetime(history["date"])
history = history.dropna(subset=["date"]).sort_values("date")

# Use the latest 90 days of observed demand.
recent = history.tail(90).copy()

if len(recent) < 30:
    raise ValueError("Insufficient recent history for this demonstration.")

daily_mean = recent["units_sold"].mean()
daily_std = recent["units_sold"].std(ddof=1)

# Normal-approximation safety stock.
safety_stock = Z_SCORE * daily_std * np.sqrt(LEAD_TIME_DAYS)

# Reorder point = expected lead-time demand + safety stock.
lead_time_demand = daily_mean * LEAD_TIME_DAYS
reorder_point = lead_time_demand + safety_stock

# Illustrative order-up-to target for a periodic review system.
target_stock = (
    daily_mean * (LEAD_TIME_DAYS + REVIEW_PERIOD_DAYS)
    + safety_stock
)

result = pd.DataFrame([{
    "item_id": item_id,
    "store_id": store_id,
    "history_start": recent["date"].min().date(),
    "history_end": recent["date"].max().date(),
    "observed_days": len(recent),
    "average_daily_demand": daily_mean,
    "daily_demand_std": daily_std,
    "assumed_lead_time_days": LEAD_TIME_DAYS,
    "assumed_review_period_days": REVIEW_PERIOD_DAYS,
    "assumed_service_level": SERVICE_LEVEL,
    "safety_stock_units": int(np.ceil(safety_stock)),
    "expected_lead_time_demand": lead_time_demand,
    "reorder_point_units": int(np.ceil(reorder_point)),
    "order_up_to_target_units": int(np.ceil(target_stock)),
    "has_actual_on_hand_inventory": False,
    "has_actual_supplier_lead_time": False,
}])

output_file = TABLES / "inventory_recommendations.csv"
result.to_csv(output_file, index=False)

print("\nINVENTORY PLANNING DEMONSTRATION")
print(result.T.to_string(header=False))
print(f"\nSaved: {output_file}")

print(
    "\nInterpretation: consider replenishment when inventory position "
    "falls to the reorder point. The order-up-to target is illustrative. "
    "Actual order quantity cannot be calculated without inventory "
    "position, outstanding purchase orders, and operational constraints."
)
