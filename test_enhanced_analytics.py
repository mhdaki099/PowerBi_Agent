"""
Test script for enhanced analytics integration
"""
import sqlite3
from enhanced_analytics import (
    get_coverage_analysis, get_coverage_loss, detect_oos_items,
    detect_seasonal_items, brand_supply_chain_dashboard
)

def test_coverage_analysis():
    """Test coverage analysis for DUP brand"""
    print("=" * 60)
    print("TEST 1: Coverage Analysis for DUP Brand")
    print("=" * 60)
    
    conn = sqlite3.connect('sales_data.db')
    
    try:
        # Test coverage for DUP brand over 1Y, 2Y, 3Y, 4Y
        coverage_df = get_coverage_analysis(conn, 'brand', 'DUP', [12, 24, 36, 48])
        print("\nCoverage Results:")
        print(coverage_df)
        print(f"\n✅ Coverage analysis completed successfully!")
        print(f"   - 12M coverage: {coverage_df[coverage_df['Time_Window']=='12M']['Coverage_Count'].values[0]} accounts")
        print(f"   - 24M coverage: {coverage_df[coverage_df['Time_Window']=='24M']['Coverage_Count'].values[0]} accounts")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def test_coverage_loss():
    """Test coverage loss detection"""
    print("\n" + "=" * 60)
    print("TEST 2: Coverage Loss for DUP Brand")
    print("=" * 60)
    
    conn = sqlite3.connect('sales_data.db')
    
    try:
        # Test coverage loss - accounts that bought historically but not recently
        loss_df = get_coverage_loss(conn, 'DUP', 'Brand', recent_months=12, historical_months=24)
        print(f"\nFound {len(loss_df)} accounts that stopped buying DUP")
        if len(loss_df) > 0:
            print("\nTop 5 Lost Accounts:")
            print(loss_df.head(5)[['Customer_Name', 'Last_Purchase_Date', 'Historical_Sales', 'Days_Since_Last_Purchase']])
            print(f"\n✅ Coverage loss analysis completed successfully!")
        else:
            print("✅ No coverage loss detected (all historical accounts are still active)")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def test_oos_detection():
    """Test OOS detection"""
    print("\n" + "=" * 60)
    print("TEST 3: OOS Detection for DUP Brand")
    print("=" * 60)
    
    conn = sqlite3.connect('sales_data.db')
    
    try:
        # Test OOS detection - items with no recent sales
        oos_df = detect_oos_items(conn, 'DUP', days_threshold=30, min_historical_sales=10000)
        print(f"\nFound {len(oos_df)} potential OOS items")
        if len(oos_df) > 0:
            print("\nTop 5 Potential OOS Items:")
            print(oos_df.head(5)[['Item_Desc', 'Historical_Sales', 'Recent_Sales', 'Days_Since_Sale', 'OOS_Risk_Level']])
            print(f"\n✅ OOS detection completed successfully!")
        else:
            print("✅ No OOS items detected (all items have recent sales)")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def test_seasonal_detection():
    """Test seasonal item detection"""
    print("\n" + "=" * 60)
    print("TEST 4: Seasonal Items Detection for DUP Brand")
    print("=" * 60)
    
    conn = sqlite3.connect('sales_data.db')
    
    try:
        # Test seasonal detection
        seasonal_df = detect_seasonal_items(conn, 'DUP', min_sales=50000, months=24)
        print(f"\nFound {len(seasonal_df)} seasonal items")
        if len(seasonal_df) > 0:
            print("\nSeasonal Items:")
            print(seasonal_df[['Item_Desc', 'Total_Sales', 'Pattern', 'Peak_Months']])
            print(f"\n✅ Seasonal detection completed successfully!")
        else:
            print("✅ No strongly seasonal items detected")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

def test_supply_chain_dashboard():
    """Test supply chain dashboard"""
    print("\n" + "=" * 60)
    print("TEST 5: Supply Chain Dashboard for DUP Brand")
    print("=" * 60)
    
    conn = sqlite3.connect('sales_data.db')
    
    try:
        # Test supply chain dashboard
        dashboard = brand_supply_chain_dashboard(conn, 'DUP', days_threshold=30)
        print(f"\nSupply Chain Dashboard Summary:")
        print(f"  - OOS Items: {dashboard['oos_items_count']}")
        print(f"  - Supply Issues: {dashboard['supply_issues_count']}")
        print(f"  - Coverage Loss: {dashboard['coverage_loss_count']}")
        print(f"  - Seasonal Items: {dashboard['seasonal_items_count']}")
        print(f"  - Anomalies: {dashboard['anomalies_count']}")
        print(f"\n✅ Supply chain dashboard completed successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    print("\n🧪 TESTING ENHANCED ANALYTICS INTEGRATION")
    print("=" * 60)
    
    test_coverage_analysis()
    test_coverage_loss()
    test_oos_detection()
    test_seasonal_detection()
    test_supply_chain_dashboard()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED!")
    print("=" * 60)
