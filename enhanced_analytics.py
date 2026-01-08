"""
Enhanced Analytics Module - Coverage, OOS Detection, and Pattern Analysis
Implements the missing features from the AI Training Framework
"""
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
import sqlite3

# =============================================================================
# 1. COVERAGE REACH FRAMEWORK
# =============================================================================

def get_coverage_analysis(conn, level='company', entity=None, time_windows=[12, 24, 36, 48], 
                          dimension='Customer_Name', filters=None):
    """
    Calculate coverage reach at Company/Brand/Item level with rolling time windows
    
    Args:
        conn: Database connection
        level: 'company', 'brand', or 'item'
        entity: Brand name or Item code (required if level != 'company')
        time_windows: List of months to look back [12, 24, 36, 48]
        dimension: What to count coverage for ('Customer_Name', 'Channel', 'Emirate', 'Group')
        filters: Dict of additional filters {'Channel': 'Hospital', 'Emirate': 'Dubai'}
    
    Returns:
        DataFrame with coverage counts for each time window
    """
    results = []
    
    for months in time_windows:
        # Build WHERE clause
        where_clauses = [f"Invoice_Date >= date('now', '-{months} months')"]
        
        if level == 'brand' and entity:
            where_clauses.append(f"Brand = '{entity}'")
        elif level == 'item' and entity:
            where_clauses.append(f"Item_Code = '{entity}'")
        
        # Add additional filters
        if filters:
            for key, value in filters.items():
                where_clauses.append(f"{key} = '{value}'")
        
        where_clause = " AND ".join(where_clauses)
        
        query = f"""
        SELECT COUNT(DISTINCT {dimension}) as Coverage_Count,
               SUM(Amount) as Total_Sales,
               COUNT(DISTINCT Invoice_No) as Transaction_Count
        FROM sales
        WHERE {where_clause}
        """
        
        df = pd.read_sql_query(query, conn)
        results.append({
            'Time_Window': f'{months}M',
            'Months': months,
            'Coverage_Count': df['Coverage_Count'].values[0],
            'Total_Sales': df['Total_Sales'].values[0],
            'Transaction_Count': df['Transaction_Count'].values[0]
        })
    
    return pd.DataFrame(results)


def get_coverage_loss(conn, entity, entity_type='Brand', recent_months=12, historical_months=24,
                     dimension='Customer_Name'):
    """
    Identify accounts/channels/emirates that bought historically but not recently
    
    Args:
        entity: Brand name or Item code
        entity_type: 'Brand' or 'Item_Code'
        recent_months: Recent period to check (default 12)
        historical_months: Historical period to compare (default 24)
        dimension: What dimension to analyze ('Customer_Name', 'Channel', 'Emirate')
    
    Returns:
        DataFrame of lost coverage with details
    """
    query = f"""
    WITH Recent AS (
        SELECT DISTINCT {dimension}
        FROM sales
        WHERE {entity_type} = '{entity}'
        AND Invoice_Date >= date('now', '-{recent_months} months')
    ),
    Historical AS (
        SELECT DISTINCT {dimension}
        FROM sales
        WHERE {entity_type} = '{entity}'
        AND Invoice_Date >= date('now', '-{historical_months} months')
        AND Invoice_Date < date('now', '-{recent_months} months')
    )
    SELECT h.{dimension}, 
           MAX(s.Invoice_Date) as Last_Purchase_Date,
           SUM(s.Amount) as Historical_Sales,
           SUM(s.Regular_Qty) as Historical_Qty,
           COUNT(DISTINCT s.Invoice_No) as Historical_Transactions,
           COUNT(DISTINCT s.Item_Code) as Items_Bought,
           julianday('now') - julianday(MAX(s.Invoice_Date)) as Days_Since_Last_Purchase
    FROM Historical h
    LEFT JOIN Recent r ON h.{dimension} = r.{dimension}
    JOIN sales s ON h.{dimension} = s.{dimension} AND s.{entity_type} = '{entity}'
    WHERE r.{dimension} IS NULL
    GROUP BY h.{dimension}
    ORDER BY Historical_Sales DESC
    """
    return pd.read_sql_query(query, conn)


def get_coverage_comparison(conn, brand1, brand2, months=12):
    """
    Compare coverage between two brands
    
    Returns:
        Dict with comparison metrics
    """
    coverage1 = get_coverage_analysis(conn, 'brand', brand1, [months])
    coverage2 = get_coverage_analysis(conn, 'brand', brand2, [months])
    
    # Get unique customers for each brand
    query = f"""
    SELECT 
        COUNT(DISTINCT CASE WHEN Brand = '{brand1}' THEN Customer_Name END) as Brand1_Only,
        COUNT(DISTINCT CASE WHEN Brand = '{brand2}' THEN Customer_Name END) as Brand2_Only,
        COUNT(DISTINCT CASE WHEN Brand IN ('{brand1}', '{brand2}') THEN Customer_Name END) as Total_Unique,
        COUNT(DISTINCT Customer_Name) as Both_Brands
    FROM sales
    WHERE Brand IN ('{brand1}', '{brand2}')
    AND Invoice_Date >= date('now', '-{months} months')
    """
    overlap = pd.read_sql_query(query, conn)
    
    return {
        'brand1': brand1,
        'brand2': brand2,
        'brand1_coverage': coverage1['Coverage_Count'].values[0],
        'brand2_coverage': coverage2['Coverage_Count'].values[0],
        'overlap': overlap['Both_Brands'].values[0],
        'brand1_exclusive': overlap['Brand1_Only'].values[0],
        'brand2_exclusive': overlap['Brand2_Only'].values[0]
    }


def get_new_vs_lost_coverage(conn, entity, entity_type='Brand', period_months=12):
    """
    Analyze new customers gained vs lost in a period
    
    Returns:
        Dict with new, lost, and retained customer counts
    """
    query = f"""
    WITH CurrentPeriod AS (
        SELECT DISTINCT Customer_Name
        FROM sales
        WHERE {entity_type} = '{entity}'
        AND Invoice_Date >= date('now', '-{period_months} months')
    ),
    PreviousPeriod AS (
        SELECT DISTINCT Customer_Name
        FROM sales
        WHERE {entity_type} = '{entity}'
        AND Invoice_Date >= date('now', '-{period_months * 2} months')
        AND Invoice_Date < date('now', '-{period_months} months')
    )
    SELECT 
        (SELECT COUNT(*) FROM CurrentPeriod c 
         LEFT JOIN PreviousPeriod p ON c.Customer_Name = p.Customer_Name 
         WHERE p.Customer_Name IS NULL) as New_Customers,
        (SELECT COUNT(*) FROM PreviousPeriod p 
         LEFT JOIN CurrentPeriod c ON p.Customer_Name = c.Customer_Name 
         WHERE c.Customer_Name IS NULL) as Lost_Customers,
        (SELECT COUNT(*) FROM CurrentPeriod c 
         JOIN PreviousPeriod p ON c.Customer_Name = p.Customer_Name) as Retained_Customers
    """
    return pd.read_sql_query(query, conn).to_dict('records')[0]


# =============================================================================
# 2. OUT-OF-STOCK (OOS) DETECTION
# =============================================================================

def detect_oos_items(conn, brand=None, days_threshold=30, min_historical_sales=10000):
    """
    Detect items with potential OOS based on sales patterns
    
    Args:
        brand: Filter by brand (optional)
        days_threshold: Days of zero sales to flag (30, 60, 90)
        min_historical_sales: Minimum historical sales to consider
    
    Returns:
        DataFrame of suspected OOS items with impact analysis
    """
    brand_filter = f"AND Brand = '{brand}'" if brand else ""
    
    query = f"""
    WITH RecentSales AS (
        SELECT Item_Code, Item_Desc, Brand,
               SUM(Amount) as Recent_Sales,
               MAX(Invoice_Date) as Last_Sale_Date,
               COUNT(DISTINCT Customer_Name) as Recent_Customers
        FROM sales
        WHERE Invoice_Date >= date('now', '-{days_threshold} days')
        {brand_filter}
        GROUP BY Item_Code, Item_Desc, Brand
    ),
    HistoricalSales AS (
        SELECT Item_Code, Item_Desc, Brand,
               SUM(Amount) as Historical_Sales,
               COUNT(DISTINCT Customer_Name) as Historical_Customers,
               COUNT(DISTINCT Invoice_No) as Historical_Transactions,
               AVG(Amount) as Avg_Monthly_Sales,
               SUM(Regular_Qty) as Historical_Qty
        FROM sales
        WHERE Invoice_Date >= date('now', '-12 months')
        AND Invoice_Date < date('now', '-{days_threshold} days')
        {brand_filter}
        GROUP BY Item_Code, Item_Desc, Brand
        HAVING Historical_Sales > {min_historical_sales}
    )
    SELECT h.Item_Code, h.Item_Desc, h.Brand,
           h.Historical_Sales,
           h.Historical_Customers as Affected_Accounts,
           h.Historical_Transactions,
           h.Avg_Monthly_Sales,
           h.Historical_Qty,
           COALESCE(r.Recent_Sales, 0) as Recent_Sales,
           r.Last_Sale_Date,
           CAST(julianday('now') - julianday(COALESCE(r.Last_Sale_Date, date('now', '-{days_threshold} days'))) AS INTEGER) as Days_Since_Sale,
           CASE 
               WHEN COALESCE(r.Recent_Sales, 0) = 0 THEN 'High'
               WHEN r.Recent_Sales < h.Avg_Monthly_Sales * 0.3 THEN 'Medium'
               ELSE 'Low'
           END as OOS_Risk_Level,
           CASE
               WHEN COALESCE(r.Recent_Sales, 0) = 0 THEN 'Increase forecast by 20% to recover lost sales'
               WHEN r.Recent_Sales < h.Avg_Monthly_Sales * 0.3 THEN 'Review stock levels and pending orders'
               ELSE 'Monitor closely'
           END as Forecast_Suggestion
    FROM HistoricalSales h
    LEFT JOIN RecentSales r ON h.Item_Code = r.Item_Code
    WHERE COALESCE(r.Recent_Sales, 0) < h.Avg_Monthly_Sales * 0.3
    ORDER BY h.Historical_Sales DESC
    """
    return pd.read_sql_query(query, conn)

def classify_decline_cause(conn, item_code):
    """
    Classify if a decline is Demand-Driven or Supply-Driven (OOS)
    
    Logic:
    - Supply-Driven if:
        1. Widespread stoppage (many accounts stopped buying at same time)
        2. Zero sales in recent period despite history
    - Demand-Driven if:
        1. Gradual decline
        2. Low sales but not zero
    """
    # 1. Check recent vs historical pattern
    query = f"""
    SELECT 
        SUM(CASE WHEN Invoice_Date >= date('now', '-30 days') THEN Amount ELSE 0 END) as Recent_Sales,
        SUM(CASE WHEN Invoice_Date >= date('now', '-90 days') AND Invoice_Date < date('now', '-30 days') THEN Amount ELSE 0 END) as Hist_Sales,
        COUNT(DISTINCT CASE WHEN Invoice_Date >= date('now', '-30 days') THEN Customer_Name END) as Recent_Cust,
        COUNT(DISTINCT CASE WHEN Invoice_Date >= date('now', '-90 days') AND Invoice_Date < date('now', '-30 days') THEN Customer_Name END) as Hist_Cust
    FROM sales
    WHERE Item_Code = '{item_code}'
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        return "Unknown - No Data"
        
    recent_sales = df['Recent_Sales'].iloc[0] or 0
    hist_sales = df['Hist_Sales'].iloc[0] or 0
    recent_cust = df['Recent_Cust'].iloc[0] or 0
    hist_cust = df['Hist_Cust'].iloc[0] or 0
    
    # Logic Rules
    if hist_sales > 1000 and recent_sales == 0:
        return "Supply-Driven (High Probability OOS) - Sudden zero sales"
        
    if hist_cust > 5 and recent_cust == 0:
        return "Supply-Driven (Widespread Stoppage) - All accounts stopped buying"
        
    if hist_sales > 0 and recent_sales < (hist_sales / 2) and recent_sales > 0:
        return "Demand-Driven (Declining Trend) - Sales dropped but not zero"
        
    return "Inconclusive - Needs manual check"


def detect_channel_oos(conn, item_code, days_threshold=30):
    """
    Detect if item sells in some channels but not others (local OOS)
    
    Args:
        item_code: Item to analyze
        days_threshold: Recent period to check
    
    Returns:
        DataFrame showing channel-level OOS risk
    """
    query = f"""
    SELECT Channel,
           SUM(CASE WHEN Invoice_Date >= date('now', '-{days_threshold} days') THEN Amount ELSE 0 END) as Recent_Sales,
           SUM(CASE WHEN Invoice_Date >= date('now', '-12 months') 
                    AND Invoice_Date < date('now', '-{days_threshold} days') THEN Amount ELSE 0 END) as Historical_Sales,
           COUNT(DISTINCT CASE WHEN Invoice_Date >= date('now', '-{days_threshold} days') THEN Customer_Name END) as Recent_Customers,
           COUNT(DISTINCT CASE WHEN Invoice_Date >= date('now', '-12 months') 
                    AND Invoice_Date < date('now', '-{days_threshold} days') THEN Customer_Name END) as Historical_Customers
    FROM sales
    WHERE Item_Code = '{item_code}'
    GROUP BY Channel
    HAVING Historical_Sales > 0
    """
    df = pd.read_sql_query(query, conn)
    df['OOS_Risk'] = (df['Historical_Sales'] > 0) & (df['Recent_Sales'] == 0)
    df['Sales_Drop_Pct'] = ((df['Historical_Sales'] - df['Recent_Sales']) / df['Historical_Sales'] * 100).round(2)
    return df


def detect_multi_account_oos(conn, brand=None, min_accounts=5, days_threshold=30):
    """
    Detect items where many accounts stopped buying (supply issue indicator)
    
    Args:
        brand: Filter by brand
        min_accounts: Minimum number of accounts that must have stopped
        days_threshold: Recent period to check
    
    Returns:
        DataFrame of items with widespread stoppage
    """
    brand_filter = f"AND Brand = '{brand}'" if brand else ""
    
    query = f"""
    WITH StoppedAccounts AS (
        SELECT Item_Code, Item_Desc, Brand, Customer_Name,
               MAX(Invoice_Date) as Last_Purchase
        FROM sales
        WHERE Invoice_Date >= date('now', '-12 months')
        {brand_filter}
        GROUP BY Item_Code, Item_Desc, Brand, Customer_Name
        HAVING MAX(Invoice_Date) < date('now', '-{days_threshold} days')
    )
    SELECT sa.Item_Code, sa.Item_Desc, sa.Brand,
           COUNT(DISTINCT sa.Customer_Name) as Stopped_Accounts,
           MAX(sa.Last_Purchase) as Most_Recent_Stop,
           SUM(s.Amount) as Lost_Sales_Potential
    FROM StoppedAccounts sa
    JOIN sales s ON sa.Item_Code = s.Item_Code 
                 AND sa.Customer_Name = s.Customer_Name
                 AND s.Invoice_Date >= date('now', '-12 months')
    GROUP BY sa.Item_Code, sa.Item_Desc, sa.Brand
    HAVING COUNT(DISTINCT sa.Customer_Name) >= {min_accounts}
    ORDER BY Stopped_Accounts DESC, Lost_Sales_Potential DESC
    """
    return pd.read_sql_query(query, conn)


def calculate_oos_impact(conn, item_code, oos_days):
    """
    Calculate financial impact of OOS
    
    Returns:
        Dict with estimated lost sales and affected customers
    """
    query = f"""
    SELECT 
        AVG(daily_sales) * {oos_days} as Estimated_Lost_Sales,
        COUNT(DISTINCT Customer_Name) as Affected_Customers,
        SUM(Amount) as Annual_Sales
    FROM (
        SELECT 
            DATE(Invoice_Date) as sale_date,
            SUM(Amount) as daily_sales,
            Customer_Name
        FROM sales
        WHERE Item_Code = '{item_code}'
        AND Invoice_Date >= date('now', '-12 months')
        GROUP BY DATE(Invoice_Date), Customer_Name
    )
    """
    return pd.read_sql_query(query, conn).to_dict('records')[0]


# =============================================================================
# 3. RUN RATE & PATTERN DETECTION
# =============================================================================

def classify_item_pattern(conn, item_code, months=12):
    """
    Classify item sales pattern: Stable, Seasonal, Fluctuating, Strange
    
    Args:
        item_code: Item to analyze
        months: Number of months to analyze
    
    Returns:
        Dict with pattern classification and metrics
    """
    query = f"""
    SELECT strftime('%Y-%m', Invoice_Date) as Month,
           SUM(Amount) as Sales,
           SUM(Regular_Qty) as Quantity,
           COUNT(DISTINCT Customer_Name) as Customers
    FROM sales
    WHERE Item_Code = '{item_code}'
    AND Invoice_Date >= date('now', '-{months} months')
    GROUP BY strftime('%Y-%m', Invoice_Date)
    ORDER BY Month
    """
    df = pd.read_sql_query(query, conn)
    
    if len(df) < 3:
        return {
            'pattern': 'Insufficient Data',
            'planning_implication': 'Need more history for analysis.',
            'confidence': 0,
            'is_seasonal': False,
            'peak_months': [],
            'has_anomalies': False,
            'details': 'Need at least 3 months of data'
        }
    
    sales = df['Sales'].values
    
    # Calculate metrics
    mean_sales = np.mean(sales)
    std_sales = np.std(sales)
    cv = std_sales / mean_sales if mean_sales > 0 else 0  # Coefficient of variation
    
    # Detect seasonality using autocorrelation
    is_seasonal = False
    seasonal_lag = None
    if len(sales) >= 12:
        # Check for 3, 6, and 12-month patterns
        for lag in [3, 6, 12]:
            if len(sales) >= lag * 2:
                correlation = np.corrcoef(sales[:lag], sales[-lag:])[0, 1]
                if correlation > 0.7:
                    is_seasonal = True
                    seasonal_lag = lag
                    break
    
    # Detect anomalies (spikes/drops) using z-score
    z_scores = np.abs(stats.zscore(sales))
    anomaly_indices = np.where(z_scores > 2.5)[0]
    has_anomalies = len(anomaly_indices) > 0
    
    # Detect trend
    if len(sales) >= 6:
        x = np.arange(len(sales))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, sales)
        has_trend = abs(r_value) > 0.7 and p_value < 0.05
        trend_direction = 'increasing' if slope > 0 else 'decreasing'
    else:
        has_trend = False
        trend_direction = 'none'
    
    # Classify pattern
    if has_anomalies:
        # Check if spike or drop
        anomaly_values = sales[anomaly_indices]
        if np.mean(anomaly_values) > mean_sales:
            pattern = 'Strange (Spike)'
        else:
            pattern = 'Strange (Drop)'
    elif is_seasonal:
        pattern = 'Seasonal'
    elif cv < 0.2:
        pattern = 'Stable'
    elif cv > 0.5:
        pattern = 'Fluctuating'
    else:
        pattern = 'Moderate Variation'
    
    # Identify peak months if seasonal
    peak_months = []
    if is_seasonal and len(df) >= 12:
        monthly_avg = df.groupby(df['Month'].str[-2:])['Sales'].mean().sort_values(ascending=False)
        peak_months = monthly_avg.head(3).index.tolist()
    
    # Determining Planning Implication
    if pattern == 'Stable':
        implication = "Predictable demand. Automate replenishment."
    elif pattern == 'Seasonal':
        implication = f"Stock up 2 months prior to peak ({', '.join(peak_months[:1])})."
    elif pattern == 'Fluctuating':
        implication = "Maintain higher safety stock to buffer volatility."
    elif 'Strange' in pattern:
        implication = "Investigate cause (Promo? OOS?). Exclude from forecast."
    else:
        implication = "Monitor variance."

    return {
        'pattern': pattern,
        'planning_implication': implication,
        'cv': round(cv, 3),
        'is_seasonal': is_seasonal,
        'seasonal_lag': seasonal_lag,
        'has_anomalies': has_anomalies,
        'anomaly_count': len(anomaly_indices),
        'has_trend': has_trend,
        'trend_direction': trend_direction,
        'peak_months': peak_months,
        'mean_sales': round(mean_sales, 2),
        'std_sales': round(std_sales, 2),
        'monthly_data': df.to_dict('records')
    }


def detect_seasonal_items(conn, brand=None, min_sales=50000, months=24):
    """
    Identify items with seasonal patterns
    
    Args:
        brand: Filter by brand
        min_sales: Minimum total sales to consider
        months: Months of history to analyze
    
    Returns:
        DataFrame of seasonal items with peak months
    """
    brand_filter = f"AND Brand = '{brand}'" if brand else ""
    
    # Get items with sufficient sales
    query = f"""
    SELECT DISTINCT Item_Code, Item_Desc, Brand,
           SUM(Amount) as Total_Sales
    FROM sales
    WHERE Invoice_Date >= date('now', '-{months} months')
    {brand_filter}
    GROUP BY Item_Code, Item_Desc, Brand
    HAVING SUM(Amount) > {min_sales}
    ORDER BY Total_Sales DESC
    """
    items_df = pd.read_sql_query(query, conn)
    
    # Analyze each item for seasonality
    seasonal_items = []
    for _, row in items_df.iterrows():
        pattern = classify_item_pattern(conn, row['Item_Code'], months)
        if pattern['is_seasonal']:
            seasonal_items.append({
                'Item_Code': row['Item_Code'],
                'Item_Desc': row['Item_Desc'],
                'Brand': row['Brand'],
                'Total_Sales': row['Total_Sales'],
                'Pattern': pattern['pattern'],
                'Peak_Months': ', '.join(pattern['peak_months']),
                'CV': pattern['cv'],
                'Seasonal_Lag': pattern['seasonal_lag']
            })
    
    return pd.DataFrame(seasonal_items)


def detect_anomalies(conn, brand=None, months=12, threshold=2.5):
    """
    Detect items with abnormal spikes or drops
    
    Args:
        brand: Filter by brand
        months: Months to analyze
        threshold: Z-score threshold for anomaly detection
    
    Returns:
        DataFrame of items with anomalies
    """
    brand_filter = f"AND Brand = '{brand}'" if brand else ""
    
    query = f"""
    SELECT Item_Code, Item_Desc, Brand,
           strftime('%Y-%m', Invoice_Date) as Month,
           SUM(Amount) as Sales
    FROM sales
    WHERE Invoice_Date >= date('now', '-{months} months')
    {brand_filter}
    GROUP BY Item_Code, Item_Desc, Brand, strftime('%Y-%m', Invoice_Date)
    """
    df = pd.read_sql_query(query, conn)
    
    anomalies = []
    for item_code in df['Item_Code'].unique():
        item_data = df[df['Item_Code'] == item_code]
        if len(item_data) < 3:
            continue
        
        sales = item_data['Sales'].values
        z_scores = np.abs(stats.zscore(sales))
        anomaly_indices = np.where(z_scores > threshold)[0]
        
        if len(anomaly_indices) > 0:
            for idx in anomaly_indices:
                anomalies.append({
                    'Item_Code': item_code,
                    'Item_Desc': item_data['Item_Desc'].iloc[0],
                    'Brand': item_data['Brand'].iloc[0],
                    'Month': item_data['Month'].iloc[idx],
                    'Sales': sales[idx],
                    'Z_Score': z_scores[idx],
                    'Type': 'Spike' if sales[idx] > np.mean(sales) else 'Drop',
                    'Deviation_Pct': ((sales[idx] - np.mean(sales)) / np.mean(sales) * 100).round(2)
                })
    
    return pd.DataFrame(anomalies)


def analyze_run_rate_stability(conn, entity, entity_type='Brand', months=12):
    """
    Analyze run-rate stability for a brand or item
    
    Returns:
        Dict with stability metrics and classification
    """
    query = f"""
    SELECT strftime('%Y-%m', Invoice_Date) as Month,
           SUM(Amount) as Sales
    FROM sales
    WHERE {entity_type} = '{entity}'
    AND Invoice_Date >= date('now', '-{months} months')
    GROUP BY strftime('%Y-%m', Invoice_Date)
    ORDER BY Month
    """
    df = pd.read_sql_query(query, conn)
    
    if len(df) < 3:
        return {'stability': 'Insufficient Data', 'confidence': 0}
    
    sales = df['Sales'].values
    cv = np.std(sales) / np.mean(sales) if np.mean(sales) > 0 else 0
    
    # Classify stability
    if cv < 0.15:
        stability = 'Very Stable'
    elif cv < 0.30:
        stability = 'Stable'
    elif cv < 0.50:
        stability = 'Moderate'
    else:
        stability = 'Unstable'
    
    return {
        'stability': stability,
        'cv': round(cv, 3),
        'mean_monthly_sales': round(np.mean(sales), 2),
        'std_monthly_sales': round(np.std(sales), 2),
        'min_monthly_sales': round(np.min(sales), 2),
        'max_monthly_sales': round(np.max(sales), 2),
        'monthly_data': df.to_dict('records')
    }

def detect_account_overstock_risk(conn, days_threshold=90):
    """
    Identify accounts at risk of overstock:
    - Recent heavy buying
    - Sudden stop in purchasing (potential stock stuck)
    """
    query = f"""
    WITH AccountStats AS (
        SELECT Customer_Name,
               AVG(Amount) as Avg_Monthly_Buy,
               MAX(Invoice_Date) as Last_Purchase
        FROM sales
        WHERE Invoice_Date >= date('now', '-12 months')
        GROUP BY Customer_Name
    ),
    RecentBuys AS (
        SELECT Customer_Name, SUM(Amount) as Recent_Total
        FROM sales
        WHERE Invoice_Date >= date('now', '-{days_threshold} days')
        GROUP BY Customer_Name
    )
    SELECT a.Customer_Name,
           a.Avg_Monthly_Buy,
           r.Recent_Total,
           a.Last_Purchase,
           (r.Recent_Total / (a.Avg_Monthly_Buy * ({days_threshold}/30.0))) as Stock_Load_Index
    FROM AccountStats a
    JOIN RecentBuys r ON a.Customer_Name = r.Customer_Name
    WHERE r.Recent_Total > (a.Avg_Monthly_Buy * ({days_threshold}/30.0) * 2.0) -- Bought > 2x normal
    AND a.Last_Purchase < date('now', '-30 days') -- Hasn't bought in last 30 days
    ORDER BY Stock_Load_Index DESC
    """
    return pd.read_sql_query(query, conn)


# =============================================================================
# 4. INTEGRATED ANALYSIS FUNCTIONS
# =============================================================================

def comprehensive_item_health_check(conn, item_code):
    """
    Complete health check for an item: coverage, OOS risk, pattern, stability
    
    Returns:
        Dict with all health metrics
    """
    # Get basic info
    query = f"""
    SELECT Item_Desc, Brand,
           SUM(Amount) as Total_Sales_12M,
           COUNT(DISTINCT Customer_Name) as Customer_Count,
           MAX(Invoice_Date) as Last_Sale_Date
    FROM sales
    WHERE Item_Code = '{item_code}'
    AND Invoice_Date >= date('now', '-12 months')
    """
    basic_info = pd.read_sql_query(query, conn).to_dict('records')[0]
    
    # Coverage analysis
    coverage = get_coverage_analysis(conn, 'item', item_code, [12, 24, 36])
    
    # Pattern analysis
    pattern = classify_item_pattern(conn, item_code, 12)
    
    # OOS risk
    oos_check = detect_oos_items(conn, days_threshold=30)
    oos_risk = oos_check[oos_check['Item_Code'] == item_code] if not oos_check.empty else None
    
    # Channel distribution
    channel_oos = detect_channel_oos(conn, item_code, 30)
    
    return {
        'item_code': item_code,
        'item_desc': basic_info['Item_Desc'],
        'brand': basic_info['Brand'],
        'total_sales_12m': basic_info['Total_Sales_12M'],
        'customer_count': basic_info['Customer_Count'],
        'last_sale_date': basic_info['Last_Sale_Date'],
        'coverage': coverage.to_dict('records'),
        'pattern': pattern,
        'oos_risk': oos_risk.to_dict('records')[0] if oos_risk is not None and not oos_risk.empty else None,
        'channel_distribution': channel_oos.to_dict('records')
    }


def brand_supply_chain_dashboard(conn, brand, days_threshold=30):
    """
    Supply chain dashboard for a brand: OOS items, coverage loss, seasonal items
    
    Returns:
        Dict with supply chain metrics
    """
    # OOS detection
    oos_items = detect_oos_items(conn, brand, days_threshold)
    
    # Multi-account OOS (supply issues)
    supply_issues = detect_multi_account_oos(conn, brand, min_accounts=5, days_threshold=days_threshold)
    
    # Coverage loss
    coverage_loss = get_coverage_loss(conn, brand, 'Brand', recent_months=12, historical_months=24)
    
    # Seasonal items
    seasonal = detect_seasonal_items(conn, brand, min_sales=50000, months=24)
    
    # Anomalies
    anomalies = detect_anomalies(conn, brand, months=12)
    
    return {
        'brand': brand,
        'oos_items_count': len(oos_items),
        'oos_items': oos_items.to_dict('records'),
        'supply_issues_count': len(supply_issues),
        'supply_issues': supply_issues.to_dict('records'),
        'coverage_loss_count': len(coverage_loss),
        'coverage_loss': coverage_loss.to_dict('records'),
        'seasonal_items_count': len(seasonal),
        'seasonal_items': seasonal.to_dict('records'),
        'anomalies_count': len(anomalies),
        'anomalies': anomalies.to_dict('records')
    }


# =============================================================================
# 5. AI PROMPT ENHANCEMENTS
# =============================================================================

ENHANCED_AI_PROMPTS = """
COVERAGE QUESTIONS:
- "What is our total company coverage in the last 12 months?" → Use get_coverage_analysis(conn, 'company', None, [12])
- "How many accounts bought Brand X in 1Y, 2Y, 3Y, 4Y?" → Use get_coverage_analysis(conn, 'brand', 'X', [12, 24, 36, 48])
- "Which accounts bought Item X historically but not recently?" → Use get_coverage_loss(conn, item_code, 'Item_Code')
- "Compare brand coverage vs company coverage" → Use get_coverage_comparison()

OOS QUESTIONS:
- "Which items had no sales in the last 30/60/90 days?" → Use detect_oos_items(conn, days_threshold=30/60/90)
- "Which SKUs stopped selling unexpectedly?" → Use detect_oos_items() + classify_item_pattern()
- "Which items show abnormal drop across many accounts?" → Use detect_multi_account_oos()
- "Is the decline demand-driven or supply-driven?" → Compare detect_oos_items() with pattern analysis

PATTERN QUESTIONS:
- "Is Item X sales stable or fluctuating?" → Use classify_item_pattern(conn, item_code)
- "Which items show seasonality?" → Use detect_seasonal_items(conn, brand)
- "Which customers buy Item Y only in certain months?" → Use classify_item_pattern() + customer-level analysis
- "Which SKUs show abnormal spikes or drops?" → Use detect_anomalies(conn, brand)
- "Which accounts are at risk of overstock or OOS?" → Use comprehensive_item_health_check()

INTEGRATED ANALYSIS:
- "Complete health check for Item X" → Use comprehensive_item_health_check(conn, item_code)
- "Supply chain dashboard for Brand X" → Use brand_supply_chain_dashboard(conn, brand)
"""

if __name__ == "__main__":
    # Example usage
    conn = sqlite3.connect('sales_data.db')
    
    # Test coverage analysis
    print("=== Coverage Analysis ===")
    coverage = get_coverage_analysis(conn, 'brand', 'DUP', [12, 24, 36, 48])
    print(coverage)
    
    # Test OOS detection
    print("\n=== OOS Detection ===")
    oos = detect_oos_items(conn, 'DUP', days_threshold=30)
    print(f"Found {len(oos)} potential OOS items")
    print(oos.head())
    
    # Test pattern detection
    print("\n=== Pattern Detection ===")
    seasonal = detect_seasonal_items(conn, 'DUP', min_sales=50000)
    print(f"Found {len(seasonal)} seasonal items")
    print(seasonal.head())
    
    conn.close()
