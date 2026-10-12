
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
CHARTS = OUTPUTS / "charts"

TABLES.mkdir(parents=True, exist_ok=True)
CHARTS.mkdir(parents=True, exist_ok=True)

parquet_file = OUTPUTS / "cleaned_sales.parquet"

if not parquet_file.exists():
    raise FileNotFoundError(
        f"Missing {parquet_file}. Run stage1_eda.py first."
    )

con = duckdb.connect()
parquet_path = str(parquet_file.resolve()).replace("\\", "/").replace("'", "''")

# Select the highest-volume item-store combination using aggregated data.
# DuckDB reads the existing Parquet; raw CSVs are not reshaped again.
print("Finding a representative high-demand product-store combination...")

candidate = con.execute(f"""
    SELECT item_id, store_id, SUM(units_sold) AS total_units
    FROM read_parquet('{parquet_path}')
    GROUP BY item_id, store_id
    ORDER BY total_units DESC
    LIMIT 1
""").df().iloc[0]

item_id = candidate["item_id"]
store_id = candidate["store_id"]

print(f"Selected item: {item_id}")
print(f"Selected store: {store_id}")
print(f"Historical units: {int(candidate['total_units']):,}")

df = con.execute(f"""
    SELECT
        date,
        units_sold,
        wday,
        month,
        year
    FROM read_parquet('{parquet_path}')
    WHERE item_id = '{item_id}'
      AND store_id = '{store_id}'
    ORDER BY date
""").df()

con.close()

df["date"] = pd.to_datetime(df["date"])
df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

if df["date"].duplicated().any():
    raise ValueError("Duplicate dates found for the selected item-store.")

if df["units_sold"].isna().any():
    raise ValueError("Missing sales values found.")

# Construct features from strictly prior observations.
for lag in [1, 7, 14, 28]:
    df[f"lag_{lag}"] = df["units_sold"].shift(lag)

for window in [7, 28]:
    df[f"rolling_mean_{window}"] = (
        df["units_sold"].shift(1).rolling(window).mean()
    )

df["day_of_week"] = df["date"].dt.dayofweek
df["month_feature"] = df["date"].dt.month
df["day_of_year"] = df["date"].dt.dayofyear

feature_columns = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_28",
    "day_of_week",
    "month_feature",
    "day_of_year",
]

df = df.dropna(subset=feature_columns).reset_index(drop=True)

# Reserve the final 28 days for validation.
validation_days = 28

if len(df) <= validation_days:
    raise ValueError("Not enough history for chronological validation.")

split = len(df) - validation_days
train = df.iloc[:split].copy()
valid = df.iloc[split:].copy()

X_train = train[feature_columns]
y_train = train["units_sold"]
X_valid = valid[feature_columns]
y_valid = valid["units_sold"]

# Baselines.
predictions = {
    "Naive (previous day)": valid["lag_1"].to_numpy(),
    "7-day moving average": valid["rolling_mean_7"].to_numpy(),
}

# Machine-learning model.
model = RandomForestRegressor(
    n_estimators=100,
    max_depth=12,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=-1,
)

print("Training Random Forest...")
model.fit(X_train, y_train)
predictions["Random Forest"] = np.maximum(
    model.predict(X_valid), 0
)

# Evaluate all models on the same validation dates.
metrics = []
prediction_data = valid[["date", "units_sold"]].copy()
prediction_data = prediction_data.rename(
    columns={"units_sold": "actual_units"}
)

for model_name, predicted in predictions.items():
    predicted = np.asarray(predicted)
    metrics.append({
        "model": model_name,
        "MAE": mean_absolute_error(y_valid, predicted),
        "RMSE": np.sqrt(mean_squared_error(y_valid, predicted)),
    })
    prediction_data[model_name] = predicted

metrics_df = pd.DataFrame(metrics).sort_values("MAE")

metrics_df.to_csv(TABLES / "forecast_model_metrics.csv", index=False)
prediction_data.to_csv(
    TABLES / "forecast_predictions.csv", index=False
)

# Plot actual versus predicted values.
plt.figure(figsize=(12, 6))
plt.plot(
    prediction_data["date"],
    prediction_data["actual_units"],
    marker="o",
    label="Actual",
)
for model_name in predictions:
    plt.plot(
        prediction_data["date"],
        prediction_data[model_name],
        label=model_name,
    )

plt.title(f"Demand Forecast — {item_id} at {store_id}")
plt.xlabel("Date")
plt.ylabel("Units Sold")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(CHARTS / "forecast_comparison.png", dpi=150)
plt.close()

print("\nVALIDATION PERIOD")
print(valid["date"].min(), "to", valid["date"].max())
print("\nMODEL COMPARISON")
print(metrics_df.to_string(index=False))
print("\nSaved:")
print(TABLES / "forecast_model_metrics.csv")
print(TABLES / "forecast_predictions.csv")
print(CHARTS / "forecast_comparison.png")
