
USE supply_chain_analytics;

-- 1. Total units sold
SELECT SUM(units_sold) AS total_units_sold
FROM daily_demand;

-- 2. Highest-demand stores
SELECT store_id, state_id, units_sold
FROM store_demand
ORDER BY units_sold DESC;

-- 3. Category demand contribution
SELECT
    cat_id,
    units_sold,
    ROUND(
        100.0 * units_sold /
        NULLIF(SUM(units_sold) OVER (), 0), 2
    ) AS demand_share_pct
FROM category_demand
ORDER BY units_sold DESC;

-- 4. Top 10 products
SELECT item_id, cat_id, dept_id, units_sold
FROM top_products
ORDER BY units_sold DESC
LIMIT 10;

-- 5. Monthly demand
SELECT
    YEAR(demand_date) AS year,
    MONTH(demand_date) AS month,
    SUM(units_sold) AS units_sold
FROM daily_demand
GROUP BY YEAR(demand_date), MONTH(demand_date)
ORDER BY year, month;

-- 6. Forecast model comparison
SELECT model, mae, rmse
FROM forecast_metrics
ORDER BY mae;

-- 7. Inventory recommendations
SELECT
    item_id,
    store_id,
    average_daily_demand,
    safety_stock_units,
    reorder_point_units,
    order_up_to_target_units
FROM inventory_recommendations;
