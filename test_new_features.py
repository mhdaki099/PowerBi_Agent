
import pandas as pd
import sqlite3
import sys
import os

sys.path.append(os.getcwd())
from enhanced_analytics import classify_item_pattern, detect_account_overstock_risk, detect_seasonal_items
from app import detect_enhanced_analytics_intent, handle_enhanced_analytics, generate_recommendations

def test_patterns_and_recommendations():
    print("Connecting to DB...")
    conn = sqlite3.connect('sales_data.db')
    cursor = conn.cursor()
    
    # 1. Test Pattern Classification
    print("\n--- Testing Pattern Classification ---")
    cursor.execute("SELECT Item_Code FROM sales ORDER BY Amount DESC LIMIT 1")
    item = cursor.fetchone()[0]
    print(f"Analyzing Item: {item}")
    
    pattern = classify_item_pattern(conn, item)
    print(f"Detected Pattern: {pattern.get('pattern')}")
    print(f"Implication: {pattern.get('planning_implication')}")
    
    if 'planning_implication' in pattern:
        print("PASS: Implication generated.")
    else:
        print("FAIL: No implication.")

    # 2. Test Seasonality Detection
    print("\n--- Testing Seasonal Detection ---")
    seasonal_df = detect_seasonal_items(conn, min_sales=50000)
    if not seasonal_df.empty:
        print(f"Found {len(seasonal_df)} seasonal items.")
        print(seasonal_df.head(2)[['Item_Code', 'Pattern', 'Peak_Months']])
    else:
        print("No seasonal items found (might be expected depending on data).")

    # 3. Test Overstock Risk
    print("\n--- Testing Overstock Risk ---")
    # This might return empty if no risk, but we test execution
    try:
        overstock_df = detect_account_overstock_risk(conn, days_threshold=90)
        print("Overstock function executed successfully.")
        if not overstock_df.empty:
            print(overstock_df.head())
        else:
            print("No overstock risks detected.")
    except Exception as e:
        print(f"FAIL: Overstock detection error: {e}")

    # 4. Test Powerful Recommendations
    print("\n--- Testing Recommendation Logic ---")
    
    # Mock Dataframe for Brand
    brand_df = pd.DataFrame({'Achievement': [75.0], 'Gap': [50000.0]})
    recs = generate_recommendations(brand_df, "Brand", "TestBrand")
    print("Brand Recommendations (<80%):")
    for r in recs: print(f"- {r}")
    
    # Mock Dataframe for Salesman
    salesman_df = pd.DataFrame({'Achievement': [65.0], 'Gap': [10000.0]})
    recs_sales = generate_recommendations(salesman_df, "Salesman", "TestSalesman")
    print("\nSalesman Recommendations (<70%):")
    for r in recs_sales: print(f"- {r}")
    
    conn.close()

if __name__ == "__main__":
    test_patterns_and_recommendations()
