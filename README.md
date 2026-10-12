# Supply Chain Analytics & Demand Forecasting

An end-to-end retail analytics project using the **M5 Forecasting dataset** to explore historical sales, compare demand forecasting models, and generate illustrative inventory planning recommendations.

## Project Overview

This project combines data analytics, machine learning, SQL, and Power BI to demonstrate a retail supply chain analytics workflow.

### Key Features

- **Exploratory Data Analysis:** Analyze daily and monthly demand, category performance, store sales, and top-selling products.
- **Data Quality Checks:** Examine duplicate keys, zero and negative sales, missing calendar values, and unmatched product prices.
- **Demand Forecasting:** Compare a naive baseline, 7-day moving average, and Random Forest model.
- **Inventory Planning:** Calculate illustrative safety stock, reorder point, and order-up-to level.
- **Power BI Dashboard:** Explore demand trends, forecasting results, product performance, and inventory recommendations.

## Tech Stack

- **Languages:** Python, SQL
- **Analytics:** Pandas, NumPy, Matplotlib
- **Database:** DuckDB; MySQL SQL scripts are also included
- **Machine Learning:** Scikit-learn, Random Forest
- **Visualization:** Power BI
- **Data Format:** CSV, Parquet

## Project Structure

```text
supply-chain-forecasting/
├── data/                     # Download the source data separately
├── outputs/
│   ├── charts/                # Generated visualizations
│   ├── reports/               # Data quality reports
│   └── tables/                # Aggregated analysis and model results
├── sql/
│   ├── 01_create_database.sql
│   └── 02_business_queries.sql
├── stage1_eda.py              # Data exploration and preparation
├── stage2_forecasting.py      # Forecast model comparison
├── stage3_inventory.py        # Inventory planning calculations
├── requirements.txt
├── .gitignore
└── README.md
```

## Key Results

Results from the current run:

- **Total recorded units sold:** 65,695,409
- **Highest-demand date:** March 6, 2016
- **Highest-volume category:** FOODS
- **Highest-volume store:** CA_3

### Forecast Model Comparison

The models were evaluated using a chronological validation window from March 28 to April 24, 2016.

| Model | MAE | RMSE |
|---|---:|---:|
| Random Forest | 23.62 | 27.68 |
| 7-day moving average | 28.97 | 36.50 |
| Naive previous-day forecast | 32.21 | 46.36 |

Lower MAE and RMSE indicate better performance. Random Forest performed best among these three models in this validation run.

**Validation note:** This is a one-step-ahead evaluation using recent observed demand to construct lag features. It should not be interpreted as a fully recursive 28-day forecast.

### Illustrative Inventory Planning

For the selected product-store combination (`FOODS_3_090`, `CA_3`), the current calculation produced:

- Safety stock: 162 units
- Reorder point: 921 units
- Order-up-to target: 1,680 units

These values use assumed lead time, review period, and service-level parameters. The source dataset does not provide actual on-hand inventory or confirmed supplier lead times, so these are **illustrative planning estimates**, not operational reorder instructions.

## How to Run

### 1. Clone the repository

```bash
git clone https://github.com/Priyankagit2004/supply-chain-analytics-forecasting.git
cd supply-chain-analytics-forecasting
```

### 2. Create and activate a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download the source dataset

Obtain the M5 Forecasting dataset from Kaggle:

https://www.kaggle.com/competitions/m5-forecasting-accuracy/data

Place the required source CSV files in the local `data/` directory. The raw data is excluded from this repository.

### 5. Run the pipeline

Run these scripts from the project root, in order:

```bash
python stage1_eda.py
python stage2_forecasting.py
python stage3_inventory.py
```

The scripts generate charts, reports, forecast metrics, predictions, and inventory recommendations under `outputs/`.

## SQL

The `sql/` directory contains a MySQL database schema and business-analysis queries. These SQL scripts are provided separately from the Python/DuckDB pipeline and may require importing the generated CSV results into the corresponding MySQL tables before running the queries.

## Limitations

- Missing product-price matches are retained as missing rather than blindly imputed.
- Zero sales do not necessarily mean an item was available; stockout information is not established by this analysis.
- Inventory recommendations depend on assumed planning parameters and lack actual stock-on-hand and supplier lead-time data.
- Forecast results apply to the selected product-store series and validation setup; they do not establish performance across every product and store.

## Author

**Priyanka Thorwate**

Electronics & Telecommunication Engineering 

