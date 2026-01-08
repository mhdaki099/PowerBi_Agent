"""
Create pre-aggregated tables for faster queries
"""
import sqlite3

conn = sqlite3.connect('sales_data.db')
cur = conn.cursor()

print("Creating optimized summary tables...")

# 1. Sales summary by Brand, Salesman, Month, Year
print("Creating sales_summary table...")
cur.execute("DROP TABLE IF EXISTS sales_summary")
cur.execute("""
CREATE TABLE sales_summary AS
SELECT 
    Year,
    Month_and_Year,
    Month_and_Year_Sort,
    Brand,
    Salesman,
    Manager,
    GM,
    Emirate,
    Channel,
    Customer_Name,
    SUM(Amount) as Total_Amount,
    SUM(Regular_Qty) as Total_Qty,
    SUM(Bonus_Qty) as Total_Bonus,
    COUNT(*) as Transaction_Count
FROM sales
GROUP BY Year, Month_and_Year, Month_and_Year_Sort, Brand, Salesman, Manager, GM, Emirate, Channel, Customer_Name
""")
print("  Done!")

# 2. Target summary
print("Creating target_summary table...")
cur.execute("DROP TABLE IF EXISTS target_summary")
cur.execute("""
CREATE TABLE target_summary AS
SELECT 
    Month_and_Year,
    Month_and_Year_Sort,
    Brand,
    Salesman,
    Manager,
    GM,
    Emirate,
    Channel,
    Customer_Name,
    SUM(Target) as Total_Target
FROM target
GROUP BY Month_and_Year, Month_and_Year_Sort, Brand, Salesman, Manager, GM, Emirate, Channel, Customer_Name
""")
print("  Done!")

# 3. Create indexes
print("Creating indexes...")
cur.execute("CREATE INDEX idx_ss_brand ON sales_summary(Brand)")
cur.execute("CREATE INDEX idx_ss_salesman ON sales_summary(Salesman)")
cur.execute("CREATE INDEX idx_ss_year ON sales_summary(Year)")
cur.execute("CREATE INDEX idx_ss_month ON sales_summary(Month_and_Year)")
cur.execute("CREATE INDEX idx_ss_join ON sales_summary(Brand, Salesman, Month_and_Year)")

cur.execute("CREATE INDEX idx_ts_brand ON target_summary(Brand)")
cur.execute("CREATE INDEX idx_ts_salesman ON target_summary(Salesman)")
cur.execute("CREATE INDEX idx_ts_join ON target_summary(Brand, Salesman, Month_and_Year)")

conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FROM sales_summary")
print(f"\nsales_summary: {cur.fetchone()[0]:,} rows")
cur.execute("SELECT COUNT(*) FROM target_summary")
print(f"target_summary: {cur.fetchone()[0]:,} rows")

cur.execute("ANALYZE")
conn.commit()
conn.close()
print("\n✓ Optimization complete!")
