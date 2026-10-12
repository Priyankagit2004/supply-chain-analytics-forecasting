
CREATE DATABASE IF NOT EXISTS supply_chain_analytics;
USE supply_chain_analytics;

CREATE TABLE IF NOT EXISTS daily_demand (
    demand_date DATE PRIMARY KEY,
    units_sold BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS category_demand (
    cat_id VARCHAR(30) PRIMARY KEY,
    units_sold BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS department_demand (
    cat_id VARCHAR(30),
    dept_id VARCHAR(30),
    units_sold BIGINT NOT NULL,
    PRIMARY KEY (cat_id, dept_id)
);

CREATE TABLE IF NOT EXISTS store_demand (
    state_id VARCHAR(10),
    store_id VARCHAR(10) PRIMARY KEY,
    units_sold BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS top_products (
    item_id VARCHAR(50) PRIMARY KEY,
    cat_id VARCHAR(30),
    dept_id VARCHAR(30),
    units_sold BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_recommendations (
    item_id VARCHAR(50),
    store_id VARCHAR(10),
    average_daily_demand DECIMAL(12,3),
    daily_demand_std DECIMAL(12,3),
    assumed_lead_time_days INT,
    safety_stock_units INT,
    reorder_point_units INT,
    order_up_to_target_units INT,
    PRIMARY KEY (item_id, store_id)
);

CREATE TABLE IF NOT EXISTS forecast_metrics (
    model VARCHAR(100) PRIMARY KEY,
    mae DECIMAL(12,4),
    rmse DECIMAL(12,4)
);
