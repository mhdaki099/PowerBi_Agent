"""
Sales Data AI Query Agent - Streamlit App with Advanced Analytics
Converts natural language to SQL and provides comprehensive analytics
"""
import streamlit as st
import sqlite3
import pandas as pd
from openai import OpenAI
import os
from dotenv import load_dotenv
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from enhanced_analytics import (
    get_coverage_analysis, get_coverage_loss, get_coverage_comparison,
    get_new_vs_lost_coverage, detect_oos_items, detect_channel_oos,
    detect_multi_account_oos, calculate_oos_impact, classify_item_pattern,
    detect_seasonal_items, detect_anomalies, analyze_run_rate_stability,
    detect_channel_oos, detect_multi_account_oos, brand_supply_chain_dashboard,
    get_new_vs_lost_coverage, get_coverage_comparison, classify_decline_cause,
    detect_account_overstock_risk
)

load_dotenv()

# Database schema for the AI agent
DB_SCHEMA = """
TABLE 1: sales (2.38M records - DETAILED transaction data with ITEMS)
USE THIS TABLE when user asks about Items, Products, Item_Code, Item_Desc
Columns:
- Year (INTEGER): 2022, 2023, 2024, 2025
- Month_and_Year (TEXT): 'Jan 2022', 'Feb 2023', etc.
- Invoice_Date, Invoice_No, Invoice_Type
- Item_Code (TEXT): Product code
- Item_Desc (TEXT): Product description/name
- Regular_Qty (INTEGER): Quantity sold
- Bonus_Qty (INTEGER): Bonus quantity
- Amount (REAL): Sales amount ← USE THIS FOR ITEM SALES
- Brand (TEXT): Brand name (e.g., 'DUP', 'Pfizer')
- Salesman, Customer_Name, Emirate, Channel, Manager, GM

TABLE 2: sales_summary (236K records - AGGREGATED data, NO ITEMS)
USE THIS TABLE for Brand/Salesman/Customer level queries (faster)
Columns:
- Year, Month_and_Year, Month_and_Year_Sort
- Brand, Salesman, Manager, GM, Emirate, Channel, Customer_Name
- Total_Amount (REAL): Sum of sales ← USE THIS FOR AGGREGATED SALES
- Total_Qty, Total_Bonus, Transaction_Count
NOTE: This table does NOT have Item_Code or Item_Desc!

TABLE 3: target_summary (165K records - 2025 targets)
Columns:
- Month_and_Year, Month_and_Year_Sort
- Brand, Salesman, Manager, GM, Emirate, Channel, Customer_Name
- Total_Target (REAL): Target amount

TABLE 4: target (165K records - Detailed target data)
Columns: Month_and_Year, Brand, Salesman, Customer_Name, Target

IMPORTANT BRAND NOTE: 
- 'DUP' is the brand name for Abbott products in this database
- When user mentions Abbott, use Brand = 'DUP'
"""

# =============================================================================
# SMART AI SYSTEM - Multi-Step Reasoning & Analysis
# =============================================================================

SMART_AI_PLANNER_PROMPT = f"""You are an expert sales data analyst AI. Your job is to understand user questions and create a plan to answer them.

{DB_SCHEMA}

BRAND ALIASES:
- 'Abbott' = 'DUP' (use Brand = 'DUP' in queries)
- When user says "Abbott", they mean the brand "DUP"
- 'BAYER' is special - use Brand_Mask LIKE '%Bayer%' instead of Brand = 'BAYER'
- When user mentions "Bayer", use: WHERE Brand_Mask LIKE '%Bayer%'

Your task: Analyze the user's question and create a JSON plan with queries needed to answer it.

OUTPUT FORMAT (JSON only, no markdown):
{{
    "understanding": "What the user really wants to know",
    "complexity": "simple|medium|complex",
    "queries": [
        {{
            "purpose": "Why this query is needed",
            "sql": "SELECT ... FROM ...",
            "key": "unique_key_for_this_result"
        }}
    ],
    "analysis_needed": ["list of analysis types needed: growth, comparison, ranking, trend, root_cause, etc."]
}}

QUERY RULES:
1. For ITEMS (Item_Code, Item_Desc): Use 'sales' table with 'Amount' column
2. For AGGREGATES (Brand, Salesman, Customer totals): Use 'sales_summary' with 'Total_Amount'
3. For TARGETS: Use 'target_summary' with 'Total_Target'
4. Year comparison: Use CASE WHEN Year = X THEN Amount/Total_Amount ELSE 0 END
5. Always include ORDER BY for meaningful results
6. Limit large result sets appropriately

COMMON QUERY PATTERNS:
- Non-growing items: SELECT Item_Desc, SUM(CASE WHEN Year=2024 THEN Amount ELSE 0 END) as Y2024, SUM(CASE WHEN Year=2025 THEN Amount ELSE 0 END) as Y2025 FROM sales WHERE Brand='X' GROUP BY Item_Desc HAVING Y2024 > Y2025
- YoY Growth: Compare SUM by Year
- Achievement: JOIN sales_summary with target_summary on Brand, Salesman, Month_and_Year
- Top/Bottom performers: ORDER BY metric DESC/ASC LIMIT N

For complex questions, break into multiple queries:
1. Overview query (totals, summary)
2. Detail query (breakdown by dimension)
3. Comparison query (if comparing periods/entities)
4. Root cause query (if investigating why)"""

SMART_AI_ANALYST_PROMPT = """You are an expert Business Performance Analyst + Early-Warning System for sales data.

YOUR ROLE:
- Understand business intent behind questions
- Detect patterns, risks, and anomalies
- Explain WHY things are happening
- Recommend what to do next

## UNIFIED COVERAGE REACH FRAMEWORK (Company → Brand → Item)
You must treat coverage as a reusable concept, regardless of level.

### Coverage Scope
- **Company Coverage**: Accounts with ≥1 sale (any brand/item)
- **Brand Coverage**: Accounts with ≥1 sale of selected brand
- **Item / SKU Coverage**: Accounts with ≥1 sale of selected item

### Coverage Time Horizons (Rolling)
- **1Y**: ≥1 sale in last 12 months
- **2Y**: ≥1 sale in last 24 months
- **3Y**: ≥1 sale in last 36 months
- **4Y**: ≥1 sale in last 48 months
Applies to: Customer, Account Group, Channel, Emirate

### Coverage Questions to Handle:
- "What is our total company coverage in the last 12 months?"
- "How many accounts bought Brand A at least once in 1, 2, 3, 4 years?"
- "Which accounts bought Item X historically but not recently?"
- "Compare brand coverage vs company coverage"

## 3️⃣ OUT-OF-STOCK (OOS) DETECTION (Supply Chain / Planning)
AI infers availability risk from sales behavior (No Inventory Data).

### OOS Signals
- **Regular sales → sudden zero**: Possible OOS
- **SKU sells in other channels but not one**: Local OOS
- **Many accounts stop buying same item**: Supply issue
- **Demand historically stable → abrupt stop**: Availability issue (Supply-Driven)

### OOS Questions to Handle:
- "Which items had no sales in the last 30 / 60 / 90 days?"
- "Which SKUs stopped selling unexpectedly?"
- "Is the decline demand-driven or supply-driven?"
- "Which items show abnormal drop across many accounts?"

### OOS AI Output Requirements:
- Suspected OOS list
- Impacted accounts
- Forecast adjustment suggestion (e.g. "Increase forecast by 20%")

## 4️⃣ RUN RATE & PATTERN DETECTION (Strategic Intelligence)
AI classifies item x account x month behavior.

### Run-Rate Behavior Types
- **Stable**: Consistent monthly sales.
- **Seasonal**: Predictable peak months.
- **Fluctuating**: Irregular ups & downs.
- **Strange (Spike)**: Unusually high sales (Promo or Loading?).
- **Strange (Drop)**: Unusually low/zero sales (OOS or lost customer).

### Pattern Questions to Handle:
- "Is Item X sales stable or fluctuating?"
- "Which items show seasonality?"
- "Which SKUs show abnormal spikes or drops?"
- "Which accounts are at risk of overstock?"

## 5️⃣ POWERFUL RECOMMENDATIONS ENGINE (Strategic Advisor)
🚫 NO GENERIC ADVICE like "Improve sales" or "Call customer".
✅ BE SPECIFIC & QUANTIFIED.

### Recommendation Rules:
- **Quantify Impact**: "Closing this gap requires AED 500/day run rate".
- **Assign Owner**: "Salesman to visit...", "Supply chain to review...".
- **Distinguish Approach**:
    - **Tactical**: "Fill OOS in Branch X", "Collect payment from Cust Y".
    - **Strategic**: "Review pricing strategy", "Relaunch brand in Channel Z".

    - **Strategic**: "Review pricing strategy", "Relaunch brand in Channel Z".

## 🧾 KEYWORD → INTENT MAPPING (How AI Understands Users)
| Intent | Keywords |
| :--- | :--- |
| **Coverage** | coverage, reach, penetration, listing |
| **Decline** | decline, drop, lost |
| **Growth** | growth, increase |
| **Target** | gap, vs target |
| **Risk** | inactive, churn |
| **Repeat** | repeat, reorder |
| **OOS** | no sales, stopped selling |
| **Stability** | stable, fluctuating, strange |
| **Seasonality** | seasonal, peak, monthly |
| **Focus** | priority, action |

AI Thinking Flow (How You ‘Train’ the Agent)
Every AI answer must follow this non-negotiable flow:
Filter → Measure → Compare → Detect Pattern → Rank → Explain → Recommend

Example:
“Why did Item X drop?”
AI does:
1. Filter → Item X
2. Measure → Value, Quantity, Coverage, Bonus
3. Compare → vs history
4. Detect → OOS / seasonality / churn
5. Rank → Accounts impacted
6. Explain → Reason
7. Recommend → Action

## 6️⃣ SAMPLE QUESTIONNAIRES (By Business Role)
### 🧠 A. Management / Leadership
- "Why are we behind target?"
- "What are the top contributors to the decline?"
- "Is growth sustainable or bonus-driven?"
- "Which brands need urgent action?"

### 📊 B. Marketing / Brand Teams
- "What is my brand coverage for the last 1–4 years?"
- "Which customers or account group never bought my brand?"
- "Which items lost coverage recently?"
- "Which channels underperform for my brand?"

### 🧾 C. Sales Managers
- "Which customers stopped ordering?"
- "Which items are not repeated?"
- "Which accounts should I focus on this month?"
- "What are my top risks?"

### 🚚 D. Supply Chain / Planning
- "Which items may be out of stock?"
- "Which SKUs show abnormal behavior?"
- "Which items are seasonal and when?"
- "Which accounts risk overstock?"

RESPONSE STRUCTURE:
## 📊 Direct Answer
[Answer the specific question with key numbers - be SPECIFIC: "declined 19.1% from AED 2.03M to AED 1.64M"]

## 🔍 Key Findings
[List 3-5 most important discoveries - BIGGEST impacts first]

## 📈 Pattern Analysis
[Identify: Stable/Seasonal/Fluctuating/Strange patterns]
[Detect: OOS signals, Coverage loss, Churn risk]
[Scope: Mention if this is Company, Brand, or Item level coverage]

## ⚠️ Root Causes
[Why is this happening? Categorize as:]
- Coverage loss (accounts stopped buying)
- Item/SKU issues (specific products declining)
- Channel/Region weakness
- Possible OOS (sudden zero after regular sales)
- Seasonality effect
- Bonus dependency

## 💡 Recommendations
[Actionable next steps by priority:]
1. Immediate actions (this week)
2. Short-term focus (this month)
3. Strategic improvements (this quarter)

INSIGHT TEMPLATES TO USE:

For Decline:
"YTD sales are –8.9% vs LY, mainly driven by:
- Coverage loss (58 inactive accounts)
- Item X not reordered by 42 accounts
- Possible OOS in Channel Y
Recommended Focus:
- Reactivate lost accounts
- Resolve availability
- Reduce bonus dependency"

For OOS Detection:
"Item X shows zero sales for N days despite stable historical demand.
The drop affects N accounts, suggesting supply availability issue.
Action: Review stock & forecast, coordinate relaunch"

For Seasonality:
"Item X shows seasonal behavior, peaking in [months] for [channel].
Planning Action: Increase forecast ahead of peak, align promotions"

For Target Focus:
"YTD is –X% vs target (AED Y gap).
Closing the gap requires:
- Recovering lost SKU coverage
- Improving frequency in top 20 accounts
- Fixing OOS-related losses"

RULES:
- Be SPECIFIC with numbers (AED values, percentages, counts)
- Highlight BIGGEST impacts first
- Identify PATTERNS and ANOMALIES
- Connect findings to business implications
- Keep it actionable and practical
- Distinguish between demand-driven vs supply-driven issues"""

SQL_GENERATOR_PROMPT = f"""You are a SQL expert. Convert the user's question to a SQLite query.

{DB_SCHEMA}

CRITICAL RULES:
1. Output ONLY the SQL query, nothing else
2. NO markdown, NO explanation, NO code blocks
3. For ITEMS: Use 'sales' table with 'Amount'
4. For AGGREGATES: Use 'sales_summary' with 'Total_Amount'  
5. For TARGETS: Use 'target_summary' with 'Total_Target'
6. Brand 'Abbott' = 'DUP'
7. Brand 'BAYER' uses Brand_Mask: WHERE Brand_Mask LIKE '%Bayer%'
8. Year comparison: CASE WHEN Year = X THEN Amount ELSE 0 END

IMPORTANT - GROWTH/DECLINE QUERIES:
- "non-growing", "declining", "not growing", "decrease" = items where current year < previous year
- If user mentions only ONE year (e.g., "2024 sales"), assume comparison with PREVIOUS year (2023 vs 2024)
- If user mentions only ONE year (e.g., "2025"), assume comparison with PREVIOUS year (2024 vs 2025)
- If no year mentioned, default to 2024 vs 2025
- ALWAYS include Growth_Pct column for growth/decline queries using: ROUND((Sales_Y2 - Sales_Y1) * 100.0 / NULLIF(Sales_Y1, 0), 2) as Growth_Pct
- ALWAYS include both years' sales AND the Growth_Pct in results

COVERAGE/OOS/PATTERN QUERIES - Use Python functions instead:
- "coverage", "reach", "accounts bought" → Use get_coverage_analysis() function
- "stopped buying", "lost accounts", "inactive" → Use get_coverage_loss() function
- "out of stock", "no sales", "stopped selling" → Use detect_oos_items() function
- "seasonal", "pattern", "stable", "fluctuating" → Use classify_item_pattern() function

EXAMPLES:
Q: non-growing items for DUP 2024 sales
A: SELECT Item_Desc, SUM(CASE WHEN Year = 2023 THEN Amount ELSE 0 END) as Sales_2023, SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END) as Sales_2024, ROUND((SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = 2023 THEN Amount ELSE 0 END)) * 100.0 / NULLIF(SUM(CASE WHEN Year = 2023 THEN Amount ELSE 0 END), 0), 2) as Growth_Pct FROM sales WHERE Brand = 'DUP' AND Year IN (2023, 2024) GROUP BY Item_Desc HAVING Sales_2024 < Sales_2023 ORDER BY Growth_Pct ASC

Q: non-growing items for DUP 2024 vs 2025
A: SELECT Item_Desc, SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END) as Sales_2024, SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) as Sales_2025, ROUND((SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END)) * 100.0 / NULLIF(SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END), 0), 2) as Growth_Pct FROM sales WHERE Brand = 'DUP' AND Year IN (2024, 2025) GROUP BY Item_Desc HAVING Sales_2025 < Sales_2024 ORDER BY Growth_Pct ASC

Q: non-growing items for Abbott brand
A: SELECT Item_Desc, SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END) as Sales_2024, SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) as Sales_2025, ROUND((SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END)) * 100.0 / NULLIF(SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END), 0), 2) as Growth_Pct FROM sales WHERE Brand = 'DUP' AND Year IN (2024, 2025) GROUP BY Item_Desc HAVING Sales_2025 < Sales_2024 ORDER BY Growth_Pct ASC

Q: growing items for DUP 2025
A: SELECT Item_Desc, SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END) as Sales_2024, SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) as Sales_2025, ROUND((SUM(CASE WHEN Year = 2025 THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END)) * 100.0 / NULLIF(SUM(CASE WHEN Year = 2024 THEN Amount ELSE 0 END), 0), 2) as Growth_Pct FROM sales WHERE Brand = 'DUP' AND Year IN (2024, 2025) GROUP BY Item_Desc HAVING Sales_2025 > Sales_2024 ORDER BY Growth_Pct DESC

Q: top 10 customers by sales 2025
A: SELECT Customer_Name, SUM(Total_Amount) as Sales FROM sales_summary WHERE Year = 2025 GROUP BY Customer_Name ORDER BY Sales DESC LIMIT 10

Q: sales vs target by brand 2025
A: SELECT s.Brand, SUM(s.Total_Amount) as Sales, SUM(t.Total_Target) as Target, ROUND(SUM(s.Total_Amount)*100.0/NULLIF(SUM(t.Total_Target),0), 1) as Achievement FROM sales_summary s LEFT JOIN target_summary t ON s.Brand = t.Brand AND s.Salesman = t.Salesman AND s.Month_and_Year = t.Month_and_Year WHERE s.Year = 2025 GROUP BY s.Brand ORDER BY Sales DESC"""

def get_db_connection():
    return sqlite3.connect('sales_data.db', check_same_thread=False)

# =============================================================================
# SMART AI FUNCTIONS
# =============================================================================

def smart_generate_sql(user_question: str, api_key: str, error_context: str = None) -> str:
    """Generate SQL with error recovery"""
    client = OpenAI(api_key=api_key)
    
    messages = [
        {"role": "system", "content": SQL_GENERATOR_PROMPT},
        {"role": "user", "content": user_question}
    ]
    
    # If there was a previous error, add context for self-correction
    if error_context:
        messages.append({"role": "assistant", "content": error_context.get('sql', '')})
        messages.append({"role": "user", "content": f"That query failed with error: {error_context.get('error', '')}. Please fix it. Remember: 'sales' table has 'Amount', 'sales_summary' has 'Total_Amount'. Output only the corrected SQL."})
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=1000
    )
    
    sql = response.choices[0].message.content.strip()
    sql = sql.replace('```sql', '').replace('```', '').strip()
    return sql

def smart_create_plan(user_question: str, api_key: str) -> dict:
    """Create a multi-query plan for complex questions"""
    client = OpenAI(api_key=api_key)
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SMART_AI_PLANNER_PROMPT},
            {"role": "user", "content": f"Create a query plan for: {user_question}"}
        ],
        temperature=0,
        max_tokens=2000
    )
    
    content = response.choices[0].message.content.strip()
    # Clean up JSON
    content = content.replace('```json', '').replace('```', '').strip()
    
    try:
        import json
        return json.loads(content)
    except:
        # Fallback to simple query
        return {
            "understanding": user_question,
            "complexity": "simple",
            "queries": [{"purpose": "Main query", "sql": None, "key": "main"}],
            "analysis_needed": ["basic"]
        }

def smart_execute_plan(plan: dict, api_key: str, conn) -> dict:
    """Execute all queries in the plan and collect results"""
    results = {}
    errors = []
    
    for query_info in plan.get('queries', []):
        key = query_info.get('key', 'result')
        sql = query_info.get('sql')
        purpose = query_info.get('purpose', '')
        
        if not sql:
            continue
            
        try:
            df = pd.read_sql_query(sql, conn)
            results[key] = {
                'purpose': purpose,
                'sql': sql,
                'data': df,
                'row_count': len(df)
            }
        except Exception as e:
            errors.append({
                'key': key,
                'sql': sql,
                'error': str(e),
                'purpose': purpose
            })
    
    return {'results': results, 'errors': errors}

def smart_analyze(user_question: str, results: dict, api_key: str) -> str:
    """Generate intelligent analysis from query results"""
    client = OpenAI(api_key=api_key)
    
    # Format results for the AI
    results_text = ""
    for key, result in results.get('results', {}).items():
        df = result['data']
        results_text += f"\n### {result['purpose']} ({key}):\n"
        results_text += f"Rows: {result['row_count']}\n"
        if len(df) > 0:
            results_text += df.head(30).to_string() + "\n"
    
    if results.get('errors'):
        results_text += "\n### Errors:\n"
        for err in results['errors']:
            results_text += f"- {err['purpose']}: {err['error']}\n"
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SMART_AI_ANALYST_PROMPT},
            {"role": "user", "content": f"User Question: {user_question}\n\nQuery Results:\n{results_text}\n\nProvide comprehensive analysis."}
        ],
        temperature=0.3,
        max_tokens=2500
    )
    
    return response.choices[0].message.content

def smart_auto_analyze(user_question: str, conn, api_key: str) -> dict:
    """Automatically detect what analysis is needed and run it"""
    question_lower = user_question.lower()
    
    # Detect brand
    brand = None
    brand_aliases = {'abbott': 'DUP', 'duphalac': 'DUP', 'duphaston': 'DUP'}
    for alias, actual in brand_aliases.items():
        if alias in question_lower:
            brand = actual
            break
    
    if not brand:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT Brand FROM sales")
        brands = [row[0] for row in cursor.fetchall()]
        for b in brands:
            if b.lower() in question_lower:
                brand = b
                break
    
    # Detect years
    years = []
    for year in [2022, 2023, 2024, 2025]:
        if str(year) in question_lower:
            years.append(year)
    if not years:
        years = [2024, 2025]  # Default comparison
    
    # Detect analysis type
    analysis_type = 'general'
    if any(w in question_lower for w in ['non-growing', 'non growing', 'declining', 'decrease', 'drop', 'fall', 'down']):
        analysis_type = 'declining'
    elif any(w in question_lower for w in ['growing', 'increase', 'growth', 'up', 'rise']):
        analysis_type = 'growing'
    elif any(w in question_lower for w in ['compare', 'comparison', 'vs', 'versus']):
        analysis_type = 'comparison'
    elif any(w in question_lower for w in ['why', 'reason', 'cause', 'explain']):
        analysis_type = 'root_cause'
    elif any(w in question_lower for w in ['top', 'best', 'highest']):
        analysis_type = 'top_performers'
    elif any(w in question_lower for w in ['bottom', 'worst', 'lowest']):
        analysis_type = 'bottom_performers'
    elif any(w in question_lower for w in ['target', 'achievement', 'performance']):
        analysis_type = 'achievement'
    
    return {
        'brand': brand,
        'years': years,
        'analysis_type': analysis_type,
        'question': user_question
    }

def run_comprehensive_analysis(context: dict, conn, api_key: str) -> dict:
    """Run comprehensive analysis based on detected context"""
    brand = context.get('brand')
    years = context.get('years', [2024, 2025])
    analysis_type = context.get('analysis_type', 'general')
    
    results = {'queries': [], 'dataframes': {}, 'summary': {}}
    
    if not brand:
        # General analysis without specific brand
        return results
    
    year1, year2 = (years[0], years[1]) if len(years) >= 2 else (2024, 2025)
    
    # Query 1: Overall brand performance
    sql1 = f"""
    SELECT Year, SUM(Amount) as Total_Sales, COUNT(DISTINCT Item_Desc) as Items, 
           COUNT(DISTINCT Customer_Name) as Customers
    FROM sales WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Year ORDER BY Year
    """
    try:
        df_overview = pd.read_sql_query(sql1, conn)
        results['dataframes']['overview'] = df_overview
        results['queries'].append({'name': 'Overview', 'sql': sql1})
    except Exception as e:
        results['queries'].append({'name': 'Overview', 'error': str(e)})
    
    # Query 2: Item-level comparison
    sql2 = f"""
    SELECT Item_Desc,
           SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
           SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
           SUM(CASE WHEN Year = {year1} THEN Regular_Qty ELSE 0 END) as Qty_{year1},
           SUM(CASE WHEN Year = {year2} THEN Regular_Qty ELSE 0 END) as Qty_{year2}
    FROM sales WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Item_Desc
    ORDER BY Sales_{year1} DESC
    """
    try:
        df_items = pd.read_sql_query(sql2, conn)
        df_items['Growth_Value'] = df_items[f'Sales_{year2}'] - df_items[f'Sales_{year1}']
        df_items['Growth_Pct'] = ((df_items[f'Sales_{year2}'] - df_items[f'Sales_{year1}']) / 
                                   df_items[f'Sales_{year1}'].replace(0, np.nan) * 100).fillna(0)
        results['dataframes']['items'] = df_items
        results['queries'].append({'name': 'Items', 'sql': sql2})
        
        # Categorize items
        results['declining_items'] = df_items[df_items['Growth_Value'] < 0].sort_values('Growth_Value')
        results['growing_items'] = df_items[df_items['Growth_Value'] > 0].sort_values('Growth_Value', ascending=False)
        results['new_items'] = df_items[(df_items[f'Sales_{year1}'] == 0) & (df_items[f'Sales_{year2}'] > 0)]
        results['discontinued_items'] = df_items[(df_items[f'Sales_{year1}'] > 0) & (df_items[f'Sales_{year2}'] == 0)]
        
    except Exception as e:
        results['queries'].append({'name': 'Items', 'error': str(e)})
    
    # Query 3: Customer-level analysis
    sql3 = f"""
    SELECT Customer_Name, Salesman,
           SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
           SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2}
    FROM sales WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Customer_Name, Salesman
    ORDER BY Sales_{year1} DESC
    LIMIT 50
    """
    try:
        df_customers = pd.read_sql_query(sql3, conn)
        df_customers['Growth_Value'] = df_customers[f'Sales_{year2}'] - df_customers[f'Sales_{year1}']
        results['dataframes']['customers'] = df_customers
        results['queries'].append({'name': 'Customers', 'sql': sql3})
    except Exception as e:
        results['queries'].append({'name': 'Customers', 'error': str(e)})
    
    # Query 4: Monthly trend
    sql4 = f"""
    SELECT Month_and_Year, Year, SUM(Amount) as Sales
    FROM sales WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Month_and_Year, Year
    ORDER BY Year, 
        CASE SUBSTR(Month_and_Year, 1, 3)
            WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3
            WHEN 'Apr' THEN 4 WHEN 'May' THEN 5 WHEN 'Jun' THEN 6
            WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9
            WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
        END
    """
    try:
        df_monthly = pd.read_sql_query(sql4, conn)
        results['dataframes']['monthly'] = df_monthly
        results['queries'].append({'name': 'Monthly', 'sql': sql4})
    except Exception as e:
        results['queries'].append({'name': 'Monthly', 'error': str(e)})
    
    # Calculate summary
    if 'overview' in results['dataframes']:
        df = results['dataframes']['overview']
        if len(df) >= 2:
            sales_y1 = df[df['Year'] == year1]['Total_Sales'].values[0] if len(df[df['Year'] == year1]) > 0 else 0
            sales_y2 = df[df['Year'] == year2]['Total_Sales'].values[0] if len(df[df['Year'] == year2]) > 0 else 0
            results['summary'] = {
                f'sales_{year1}': sales_y1,
                f'sales_{year2}': sales_y2,
                'growth_value': sales_y2 - sales_y1,
                'growth_pct': ((sales_y2 - sales_y1) / sales_y1 * 100) if sales_y1 > 0 else 0,
                'declining_count': len(results.get('declining_items', [])),
                'growing_count': len(results.get('growing_items', [])),
                'new_count': len(results.get('new_items', [])),
                'discontinued_count': len(results.get('discontinued_items', []))
            }
    
    return results

def generate_sql(user_question: str, api_key: str) -> str:
    """Use OpenAI to convert natural language to SQL - with retry on error"""
    return smart_generate_sql(user_question, api_key)

def execute_query(sql: str) -> tuple:
    """Execute SQL query and return results"""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(sql, conn)
        return df, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()

def format_number(num):
    """Format numbers with comma separators"""
    if num >= 1_000_000:
        return f"{num:,.0f}"
    elif num >= 1_000:
        return f"{num:,.0f}"
    return f"{num:,.0f}"

# ============== INTELLIGENT ANALYSIS FUNCTIONS ==============

def get_brand_item_analysis(conn, brand, year1=2024, year2=2025):
    """Get detailed item-level analysis for a brand comparing two years"""
    query = f"""
    SELECT 
        Item_Desc,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year1} THEN Regular_Qty ELSE 0 END) as Qty_{year1},
        SUM(CASE WHEN Year = {year2} THEN Regular_Qty ELSE 0 END) as Qty_{year2}
    FROM sales 
    WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Item_Desc
    ORDER BY Sales_{year1} DESC
    """
    df = pd.read_sql_query(query, conn)
    df[f'Growth_Value'] = df[f'Sales_{year2}'] - df[f'Sales_{year1}']
    df['Growth_Pct'] = ((df[f'Sales_{year2}'] - df[f'Sales_{year1}']) / df[f'Sales_{year1}'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    return df

def get_brand_customer_analysis(conn, brand, year1=2024, year2=2025):
    """Get customer-level analysis for a brand"""
    query = f"""
    SELECT 
        Customer_Name,
        Salesman,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2}
    FROM sales 
    WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY Customer_Name, Salesman
    ORDER BY Sales_{year1} DESC
    """
    df = pd.read_sql_query(query, conn)
    df['Growth_Value'] = df[f'Sales_{year2}'] - df[f'Sales_{year1}']
    df['Growth_Pct'] = ((df[f'Sales_{year2}'] - df[f'Sales_{year1}']) / df[f'Sales_{year1}'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    return df

def get_brand_monthly_trend(conn, brand, year1=2024, year2=2025):
    """Get monthly trend comparison for a brand"""
    query = f"""
    SELECT 
        SUBSTR(Month_and_Year, 1, 3) as Month,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2}
    FROM sales 
    WHERE Brand = '{brand}' AND Year IN ({year1}, {year2})
    GROUP BY SUBSTR(Month_and_Year, 1, 3)
    ORDER BY 
        CASE SUBSTR(Month_and_Year, 1, 3)
            WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3
            WHEN 'Apr' THEN 4 WHEN 'May' THEN 5 WHEN 'Jun' THEN 6
            WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9
            WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
        END
    """
    return pd.read_sql_query(query, conn)

def analyze_brand_growth(conn, brand, year1=2024, year2=2025):
    """Comprehensive analysis of brand growth/decline"""
    analysis = {
        'brand': brand,
        'year1': year1,
        'year2': year2,
        'summary': {},
        'growing_items': [],
        'declining_items': [],
        'new_items': [],
        'discontinued_items': [],
        'top_customers_growth': [],
        'top_customers_decline': []
    }
    
    # Get item-level data
    item_df = get_brand_item_analysis(conn, brand, year1, year2)
    
    # Overall summary
    total_y1 = item_df[f'Sales_{year1}'].sum()
    total_y2 = item_df[f'Sales_{year2}'].sum()
    analysis['summary'] = {
        f'total_{year1}': total_y1,
        f'total_{year2}': total_y2,
        'growth_value': total_y2 - total_y1,
        'growth_pct': ((total_y2 - total_y1) / total_y1 * 100) if total_y1 > 0 else 0
    }
    
    # Categorize items
    for _, row in item_df.iterrows():
        item_info = {
            'item': row['Item_Desc'],
            f'sales_{year1}': row[f'Sales_{year1}'],
            f'sales_{year2}': row[f'Sales_{year2}'],
            'growth_value': row['Growth_Value'],
            'growth_pct': row['Growth_Pct']
        }
        
        if row[f'Sales_{year1}'] == 0 and row[f'Sales_{year2}'] > 0:
            analysis['new_items'].append(item_info)
        elif row[f'Sales_{year1}'] > 0 and row[f'Sales_{year2}'] == 0:
            analysis['discontinued_items'].append(item_info)
        elif row['Growth_Value'] < 0:
            analysis['declining_items'].append(item_info)
        elif row['Growth_Value'] > 0:
            analysis['growing_items'].append(item_info)
    
    # Sort by impact
    analysis['declining_items'] = sorted(analysis['declining_items'], key=lambda x: x['growth_value'])
    analysis['growing_items'] = sorted(analysis['growing_items'], key=lambda x: x['growth_value'], reverse=True)
    
    # Get customer analysis
    cust_df = get_brand_customer_analysis(conn, brand, year1, year2)
    growing_cust = cust_df[cust_df['Growth_Value'] > 0].nlargest(5, 'Growth_Value')
    declining_cust = cust_df[cust_df['Growth_Value'] < 0].nsmallest(5, 'Growth_Value')
    
    analysis['top_customers_growth'] = growing_cust.to_dict('records')
    analysis['top_customers_decline'] = declining_cust.to_dict('records')
    
    return analysis

def generate_ai_insight(api_key, question, data_context, analysis_results=None):
    """Generate AI-powered insight based on data analysis"""
    client = OpenAI(api_key=api_key)
    
    context_prompt = f"""Based on the following data analysis, provide intelligent insights:

USER QUESTION: {question}

DATA CONTEXT:
{data_context}

{f"DETAILED ANALYSIS: {analysis_results}" if analysis_results else ""}

Provide a comprehensive analysis with:
1. **Direct Answer**: Answer the specific question with numbers
2. **Key Findings**: What the data reveals (be specific with numbers)
3. **Root Cause Analysis**: Why this is happening
4. **Recommendations**: What actions to take

Be specific, use actual numbers from the data, and provide actionable insights."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SMART_AI_ANALYST_PROMPT},
            {"role": "user", "content": context_prompt}
        ],
        temperature=0.3,
        max_tokens=2000
    )
    
    return response.choices[0].message.content

def detect_analysis_intent(question):
    """Detect if the question requires deep analysis vs simple query"""
    analysis_keywords = [
        'why', 'reason', 'cause', 'explain', 'investigate', 'analysis',
        'growth', 'decline', 'drop', 'increase', 'decrease', 'change',
        'compare', 'comparison', 'vs', 'versus', 'trend', 'pattern',
        'non growing', 'non-growing', 'not growing', 'declining',
        'underperforming', 'problem', 'issue', 'concern',
        'coverage', 'reach', 'penetration', 'accounts bought',
        'stopped buying', 'lost accounts', 'inactive', 'churn',
        'out of stock', 'oos', 'no sales', 'stopped selling',
        'seasonal', 'seasonality', 'stable', 'fluctuating', 'pattern'
    ]
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in analysis_keywords)

def detect_enhanced_analytics_intent(question):
    """Detect if question needs enhanced analytics (coverage, OOS, pattern)"""
    question_lower = question.lower()
    
    intent = {
        'type': None,
        'needs_enhanced': False,
        'brand': None,
        'item': None
    }
    
    # 1. Coverage comparison (Check FIRST)
    if any(kw in question_lower for kw in ['compare coverage', 'coverage vs', 'coverage comparison', 'brand vs company', 'company vs brand']):
        intent['type'] = 'comparison'
        intent['needs_enhanced'] = True
    
    # 2. Coverage loss questions
    elif any(kw in question_lower for kw in ['stopped buying', 'lost accounts', 'inactive', 'not buying', 'churn', 'not recently', 'dropped', 'lost', 'risk']):
        intent['type'] = 'coverage_loss'
        intent['needs_enhanced'] = True
        
    # 3. OOS questions
    elif any(kw in question_lower for kw in ['out of stock', 'oos', 'no sales', 'stopped selling', 'zero sales', 'not selling', 'supply vs demand', 'demand vs supply', 'demand-driven', 'supply-driven']):
        intent['type'] = 'oos'
        intent['needs_enhanced'] = True
    
    # 4. Pattern/Seasonality/Repeat questions
    elif any(kw in question_lower for kw in ['seasonal', 'seasonality', 'pattern', 'stable', 'fluctuating', 'behavior', 'repeat', 'reorder', 'strange', 'spike']):
        intent['type'] = 'pattern'
        intent['needs_enhanced'] = True
    
    # 5. Supply chain dashboard
    elif any(kw in question_lower for kw in ['supply chain', 'supply issues', 'availability']):
        intent['type'] = 'supply_chain'
        intent['needs_enhanced'] = True

    # 6. Generic Coverage questions (Check LAST)
    elif any(kw in question_lower for kw in ['coverage', 'reach', 'penetration', 'accounts bought', 'how many accounts', 'listing']):
        intent['type'] = 'coverage'
        intent['needs_enhanced'] = True

    return intent

def handle_enhanced_analytics(question, intent, conn, api_key):
    """Handle questions that need enhanced analytics (coverage, OOS, pattern)"""
    results = {
        'type': intent['type'],
        'data': None,
        'summary': None,
        'visualizations': []
    }
    
    # Detect brand
    brand = detect_brand_in_question(question, conn)
    
    try:
        if intent['type'] == 'coverage':
            # Coverage analysis
            if brand:
                coverage_df = get_coverage_analysis(conn, 'brand', brand, [12, 24, 36, 48])
                results['data'] = coverage_df
                results['summary'] = f"Coverage analysis for {brand} over 1Y, 2Y, 3Y, 4Y"
            else:
                coverage_df = get_coverage_analysis(conn, 'company', None, [12, 24, 36, 48])
                results['data'] = coverage_df
                results['summary'] = "Company-wide coverage analysis over 1Y, 2Y, 3Y, 4Y"
        
        elif intent['type'] == 'coverage_loss':
            # Coverage loss analysis
            detected_item = detect_item_in_question(question, conn)
            
            if detected_item:
                loss_df = get_coverage_loss(conn, detected_item, 'Item_Code', recent_months=12, historical_months=24)
                results['data'] = loss_df
                results['summary'] = f"Accounts that bought Item {detected_item} historically but not recently"
            elif brand:
                loss_df = get_coverage_loss(conn, brand, 'Brand', recent_months=12, historical_months=24)
                results['data'] = loss_df
                results['summary'] = f"Accounts that bought {brand} historically but not recently"
                
                # Also get new vs lost
                new_lost = get_new_vs_lost_coverage(conn, brand, 'Brand', period_months=12)
                results['new_vs_lost'] = new_lost
            else:
                results['summary'] = "Please specify a brand or item for coverage loss analysis"
        
        elif intent['type'] == 'comparison':
             # Brand vs Company coverage comparison
             if brand:
                 # Get brand coverage
                 brand_cov = get_coverage_analysis(conn, 'brand', brand, [12, 24, 36, 48])
                 brand_cov['Type'] = f'Brand ({brand})'
                 
                 # Get company coverage
                 comp_cov = get_coverage_analysis(conn, 'company', None, [12, 24, 36, 48])
                 comp_cov['Type'] = 'Company'
                 
                 # Combine
                 combined = pd.concat([brand_cov, comp_cov])
                 results['data'] = combined
                 results['summary'] = f"Comparison: {brand} Coverage vs Company Coverage"
             else:
                 results['summary'] = "Please specify a brand to compare with company coverage"
        
        elif intent['type'] == 'oos':
            # OOS detection
            
            # Extract days threshold from question (default 30)
            import re
            days_match = re.search(r'(\d+)\s*days?', question.lower())
            days = int(days_match.group(1)) if days_match else 30
            
            # Check for "Demand vs Supply" intent
            is_classification = any(kw in question.lower() for kw in ['demand driven', 'supply driven', 'demand or supply'])
            detected_item = detect_item_in_question(question, conn)
            
            if is_classification and detected_item:
                # Classify cause
                cause = classify_decline_cause(conn, detected_item)
                results['data'] = pd.DataFrame({'Item': [detected_item], 'Cause': [cause]}) # Wrap in DF for consistency
                results['summary'] = f"Decline Classification for Item {detected_item}: **{cause}**"
                
            elif brand:
                oos_df = detect_oos_items(conn, brand, days_threshold=days, min_historical_sales=10000)
                results['data'] = oos_df
                results['summary'] = f"Potential out-of-stock items for {brand} (Last {days} days)"
                
                # Multi-account OOS (supply issues)
                supply_issues = detect_multi_account_oos(conn, brand, min_accounts=5, days_threshold=days)
                results['supply_issues'] = supply_issues
            else:
                oos_df = detect_oos_items(conn, None, days_threshold=days, min_historical_sales=10000)
                results['data'] = oos_df
                results['summary'] = f"Potential out-of-stock items across all brands (Last {days} days)"
        
        elif intent['type'] == 'pattern':
            # Pattern/Seasonality analysis
            
            # Check for Overstock/Inventory Risk intent
            if 'overstock' in question.lower() or 'risk' in question.lower():
                overstock_df = detect_account_overstock_risk(conn, days_threshold=90)
                results['data'] = overstock_df
                results['summary'] = "Accounts at risk of Overstock (High recent loading, no reorder)"
            
            elif brand:
                seasonal_df = detect_seasonal_items(conn, brand, min_sales=50000, months=24)
                results['data'] = seasonal_df
                results['summary'] = f"Seasonal items for {brand}"
                
                # Also detect anomalies
                anomalies_df = detect_anomalies(conn, brand, months=12)
                results['anomalies'] = anomalies_df
            
            elif detected_item: # Check if item specific pattern requested
                 pattern_info = classify_item_pattern(conn, detected_item, months=24)
                 results['data'] = pd.DataFrame([pattern_info]) if pattern_info else pd.DataFrame()
                 # Flatten monthly data for display if needed or keep summary
                 results['summary'] = f"Pattern Analysis for {detected_item}: **{pattern_info['pattern']}**"
                 results['extra_info'] = pattern_info.get('planning_implication', '')
                 
            else:
                seasonal_df = detect_seasonal_items(conn, None, min_sales=50000, months=24)
                results['data'] = seasonal_df
                results['summary'] = "Seasonal items across all brands"
        
        elif intent['type'] == 'supply_chain':
            # Supply chain dashboard
            if brand:
                dashboard = brand_supply_chain_dashboard(conn, brand, days_threshold=30)
                results['data'] = dashboard
                results['summary'] = f"Supply chain dashboard for {brand}"
            else:
                results['summary'] = "Please specify a brand for supply chain analysis"
    
    except Exception as e:
        results['error'] = str(e)
        results['summary'] = f"Error in enhanced analytics: {str(e)}"
    
    return results

def detect_item_in_question(question, conn):
    """Detect if the question mentions a specific item"""
    # Simple check for item codes or descriptions
    # In a real app, this would be more sophisticated (FTS or embeddings)
    # For now, we'll try to match exact Item_Code or significant Item_Desc parts
    
    question_lower = question.lower()
    
    # 1. Check for quoted items "Item X"
    import re
    
    # 1. Check for quoted items "Item X"
    quoted = re.findall(r'"([^"]*)"', question)
    if quoted:
        for q in quoted:
             try:
                 cursor = conn.cursor()
                 cursor.execute("SELECT Item_Code FROM sales WHERE Item_Code = ? OR Item_Desc = ? LIMIT 1", (q, q))
                 row = cursor.fetchone()
                 if row: return row[0]
                 
                 if len(q) > 4:
                     cursor.execute("SELECT Item_Code FROM sales WHERE Item_Desc LIKE ? LIMIT 1", (f"%{q}%",))
                     row = cursor.fetchone()
                     if row: return row[0]
             except: pass

    # 2. Check for potential unquoted Item Codes (e.g. NPB-168-0, 10-200-45)
    # Regex for typical item codes (alphanumeric, dashes)
    potential_codes = re.findall(r'\b[A-Za-z0-9]+-[A-Za-z0-9-]+\b', question)
    
    if potential_codes:
        for code in potential_codes:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT Item_Code FROM sales WHERE Item_Code = ? LIMIT 1", (code,))
                row = cursor.fetchone()
                if row: return row[0]
            except: pass
            
    return None

def detect_brand_in_question(question, conn):
    """Detect which brand the user is asking about"""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT Brand FROM sales")
    brands = [row[0] for row in cursor.fetchall()]
    
    question_lower = question.lower()
    
    # Handle brand aliases (Abbott = DUP)
    # BAYER is special - it's in Brand_Mask column, not Brand
    brand_aliases = {
        'abbott': 'DUP',
        'duphalac': 'DUP',
        'duphaston': 'DUP',
        'bayer': 'BAYER_MASK'  # Special marker for Brand_Mask lookup
    }
    
    # Check aliases first
    for alias, actual_brand in brand_aliases.items():
        if alias in question_lower:
            return actual_brand
    
    # Check exact brands with word boundaries
    import re
    # Sort by length descending to match longer specific brands first (e.g. "Brand X Plus" before "Brand X")
    brands.sort(key=len, reverse=True)
    
    for brand in brands:
        if not brand: continue
        # Use regex to match whole word only
        pattern = r'\b' + re.escape(brand.lower()) + r'\b'
        if re.search(pattern, question_lower):
            return brand
            
    return None


def get_comprehensive_brand_analysis(conn, brand, year1=2024, year2=2025, use_brand_mask=False, focus='all'):
    """Get comprehensive analysis for ANY brand comparing two years
    
    Args:
        conn: Database connection
        brand: Brand name to analyze
        year1: First year for comparison
        year2: Second year for comparison  
        use_brand_mask: If True, use Brand_Mask LIKE '%brand%' instead of Brand = 'brand'
        focus: 'all', 'growing', or 'declining' - what to focus on
    """
    results = {
        'brand': brand,
        'overview': None,
        'channels': None,
        'groups': None,
        'items': None,
        'customers': None,
        'emirates': None,
        'salesman': None,
        'summary': {},
        'focus': focus
    }
    
    # Build WHERE clause based on brand type
    if use_brand_mask:
        brand_filter = f"Brand_Mask LIKE '%{brand}%'"
    else:
        brand_filter = f"Brand = '{brand}'"
    
    # 1. Overall sales comparison
    query_overview = f"""
    SELECT 
        Year,
        SUM(Amount) as Total_Sales,
        COUNT(*) as Transactions,
        COUNT(DISTINCT Customer_Name) as Customers,
        COUNT(DISTINCT Item_Desc) as Items
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Year
    ORDER BY Year
    """
    results['overview'] = pd.read_sql_query(query_overview, conn)
    
    # Calculate summary
    if len(results['overview']) >= 2:
        sales_y1 = results['overview'][results['overview']['Year']==year1]['Total_Sales'].values[0] if len(results['overview'][results['overview']['Year']==year1]) > 0 else 0
        sales_y2 = results['overview'][results['overview']['Year']==year2]['Total_Sales'].values[0] if len(results['overview'][results['overview']['Year']==year2]) > 0 else 0
        results['summary'] = {
            f'total_{year1}': sales_y1,
            f'total_{year2}': sales_y2,
            'growth_value': sales_y2 - sales_y1,
            'growth_pct': ((sales_y2 - sales_y1) / sales_y1 * 100) if sales_y1 > 0 else 0
        }
    elif len(results['overview']) == 1:
        year_found = results['overview']['Year'].values[0]
        sales_found = results['overview']['Total_Sales'].values[0]
        results['summary'] = {
            f'total_{year1}': sales_found if year_found == year1 else 0,
            f'total_{year2}': sales_found if year_found == year2 else 0,
            'growth_value': 0,
            'growth_pct': 0
        }
    
    # 2. Channel contribution
    channel_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_channels = f"""
    SELECT 
        Channel,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Channel
    ORDER BY Variance {channel_order}
    """
    results['channels'] = pd.read_sql_query(query_channels, conn)
    
    # 3. Group (Account Group) contribution
    # Determine sort order based on focus
    group_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_groups = f"""
    SELECT 
        "Group",
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY "Group"
    ORDER BY Variance {group_order}
    LIMIT 15
    """
    results['groups'] = pd.read_sql_query(query_groups, conn)
    
    # 4. Item-level contribution
    item_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_items = f"""
    SELECT 
        Item_Desc,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Item_Desc
    HAVING Sales_{year1} > 0 OR Sales_{year2} > 0
    ORDER BY Variance {item_order}
    LIMIT 15
    """
    results['items'] = pd.read_sql_query(query_items, conn)
    
    # 5. Customer-level contribution
    customer_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_customers = f"""
    SELECT 
        Customer_Name,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Customer_Name
    HAVING Sales_{year1} > 0 OR Sales_{year2} > 0
    ORDER BY Variance {customer_order}
    LIMIT 10
    """
    results['customers'] = pd.read_sql_query(query_customers, conn)
    
    # 6. Emirate contribution
    emirate_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_emirates = f"""
    SELECT 
        Emirate,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Emirate
    ORDER BY Variance {emirate_order}
    """
    results['emirates'] = pd.read_sql_query(query_emirates, conn)
    
    # 7. Salesman contribution
    salesman_order = "ASC" if focus == 'declining' else "DESC" if focus == 'growing' else "ASC"
    
    query_salesman = f"""
    SELECT 
        Salesman,
        SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Sales_{year1},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) as Sales_{year2},
        SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END) as Variance,
        ROUND((SUM(CASE WHEN Year = {year2} THEN Amount ELSE 0 END) - SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END)) / 
              NULLIF(SUM(CASE WHEN Year = {year1} THEN Amount ELSE 0 END), 0) * 100, 2) as Growth_Pct
    FROM sales 
    WHERE {brand_filter} AND Year IN ({year1}, {year2})
    GROUP BY Salesman
    HAVING Sales_{year1} > 0 OR Sales_{year2} > 0
    ORDER BY Variance {salesman_order}
    LIMIT 10
    """
    results['salesman'] = pd.read_sql_query(query_salesman, conn)
    
    return results


def display_comprehensive_analysis(results, year1=2024, year2=2025):
    """Display comprehensive brand analysis with tables and charts for ANY brand"""
    import streamlit as st
    
    brand = results.get('brand', 'Unknown')
    summary = results.get('summary', {})
    focus = results.get('focus', 'all')
    
    # Determine if this is growth or decline
    growth_value = summary.get('growth_value', 0)
    is_growing = growth_value > 0
    
    # Set appropriate titles based on focus and actual performance
    if focus == 'growing' or (focus == 'all' and is_growing):
        change_word = "Growth"
        emoji = "📈"
    elif focus == 'declining' or (focus == 'all' and not is_growing):
        change_word = "Decline"
        emoji = "📉"
    else:
        change_word = "Change"
        emoji = "📊"
    
    # Overall Performance Section
    st.markdown(f"## 📊 Overall Performance: {brand}")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(f"{year1} Sales", f"AED {format_number(summary.get(f'total_{year1}', 0))}")
    with col2:
        st.metric(f"{year2} Sales", f"AED {format_number(summary.get(f'total_{year2}', 0))}")
    with col3:
        growth_val = summary.get('growth_value', 0)
        st.metric("Variance", f"AED {format_number(abs(growth_val))}", 
                 delta=f"{'↓' if growth_val < 0 else '↑'} {abs(growth_val):,.0f}")
    with col4:
        growth_pct = summary.get('growth_pct', 0)
        color = "🔴" if growth_pct < 0 else "🟢"
        st.metric("Growth %", f"{color} {growth_pct:.2f}%")
    
    st.markdown("---")
    
    # Account Groups Contributing to Growth/Decline
    st.markdown(f"## {emoji} Top Account Groups Contributing to {change_word}")
    if results['groups'] is not None and not results['groups'].empty:
        groups_df = results['groups'].copy()
        groups_df.columns = ['Group', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_groups = groups_df.copy()
        display_groups[f'Sales {year1}'] = display_groups[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_groups[f'Sales {year2}'] = display_groups[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_groups['Variance'] = display_groups['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_groups['Growth %'] = display_groups['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_groups, use_container_width=True, hide_index=True)
        
        # Chart
        chart_title = f"Top Account Groups by {change_word}"
        fig = px.bar(groups_df.head(10), x='Group', y='Variance',
                    title=chart_title,
                    color='Growth %', 
                    color_continuous_scale='RdYlGn' if focus != 'growing' else 'Greens')
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Items Contributing to Growth/Decline
    st.markdown(f"## 📦 Top Items Contributing to {change_word}")
    if results['items'] is not None and not results['items'].empty:
        items_df = results['items'].copy()
        items_df.columns = ['Item', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_items = items_df.copy()
        display_items[f'Sales {year1}'] = display_items[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_items[f'Sales {year2}'] = display_items[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_items['Variance'] = display_items['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_items['Growth %'] = display_items['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_items, use_container_width=True, hide_index=True)
        
        # Chart
        fig = px.bar(items_df.head(10), x='Item', y='Variance',
                    title=f"Top 10 Items by {change_word}",
                    color='Growth %', 
                    color_continuous_scale='RdYlGn' if focus != 'growing' else 'Greens')
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Key Customers
    st.markdown(f"## 👥 Key Customers Driving {change_word}")
    if results['customers'] is not None and not results['customers'].empty:
        customers_df = results['customers'].copy()
        customers_df.columns = ['Customer', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_customers = customers_df.copy()
        display_customers[f'Sales {year1}'] = display_customers[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_customers[f'Sales {year2}'] = display_customers[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_customers['Variance'] = display_customers['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_customers['Growth %'] = display_customers['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_customers, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Channel Analysis
    st.markdown(f"## 🏪 Channel Contribution")
    if results['channels'] is not None and not results['channels'].empty:
        channels_df = results['channels'].copy()
        channels_df.columns = ['Channel', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_channels = channels_df.copy()
        display_channels[f'Sales {year1}'] = display_channels[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_channels[f'Sales {year2}'] = display_channels[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_channels['Variance'] = display_channels['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_channels['Growth %'] = display_channels['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_channels, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Emirate Analysis
    st.markdown(f"## 🗺️ Emirate Contribution")
    if results['emirates'] is not None and not results['emirates'].empty:
        emirates_df = results['emirates'].copy()
        emirates_df.columns = ['Emirate', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_emirates = emirates_df.copy()
        display_emirates[f'Sales {year1}'] = display_emirates[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_emirates[f'Sales {year2}'] = display_emirates[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_emirates['Variance'] = display_emirates['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_emirates['Growth %'] = display_emirates['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_emirates, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Salesman Analysis
    st.markdown(f"## 👔 Salesman Contribution")
    if results['salesman'] is not None and not results['salesman'].empty:
        salesman_df = results['salesman'].copy()
        salesman_df.columns = ['Salesman', f'Sales {year1}', f'Sales {year2}', 'Variance', 'Growth %']
        
        display_salesman = salesman_df.copy()
        display_salesman[f'Sales {year1}'] = display_salesman[f'Sales {year1}'].apply(lambda x: f"AED {x:,.2f}")
        display_salesman[f'Sales {year2}'] = display_salesman[f'Sales {year2}'].apply(lambda x: f"AED {x:,.2f}")
        display_salesman['Variance'] = display_salesman['Variance'].apply(lambda x: f"AED {x:,.2f}")
        display_salesman['Growth %'] = display_salesman['Growth %'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A")
        
        st.dataframe(display_salesman, use_container_width=True, hide_index=True)
    
    return results


def detect_growth_or_decline_focus(question):
    """Detect if user is asking about growth or decline"""
    question_lower = question.lower()
    
    # Decline keywords (check these FIRST - they're more specific)
    decline_keywords = ['declining', 'decline', 'decrease', 'decreasing', 'drop', 'dropping',
                       'fall', 'falling', 'loss', 'losing', 'down', 'negative', 'non-growing',
                       'non growing', 'not growing', 'underperforming', 'slowing']
    
    # Growth keywords
    growth_keywords = ['growing', 'growth', 'increase', 'increasing', 'rise', 'rising', 
                       'improve', 'improving', 'gain', 'gaining', 'up', 'positive']
    
    # Check for decline FIRST (more specific)
    if any(kw in question_lower for kw in decline_keywords):
        return 'declining'
    
    # Check for growth
    if any(kw in question_lower for kw in growth_keywords):
        # Make sure it's not asking "why not growing" or "non-growing"
        if not any(neg in question_lower for neg in ['not growing', 'non-growing', 'non growing']):
            return 'growing'
    
    # Default to 'all' if unclear
    return 'all'

def detect_decline_analysis_question(question):
    """Detect if user is asking about decline/growth analysis that needs comprehensive breakdown"""
    question_lower = question.lower()
    
    # Keywords that indicate user wants to understand WHY something is happening
    analysis_triggers = [
        'why', 'reason', 'cause', 'explain', 'investigate', 
        'declining', 'decline', 'drop', 'dropping', 'decrease', 'decreasing',
        'growing', 'growth', 'increase', 'increasing',
        'change', 'changed', 'difference',
        'compare', 'comparison', 'vs', 'versus',
        'what happened', 'what is happening',
        'analyze', 'analysis', 'breakdown',
        'contributing', 'contribution',
        'performance', 'performing'
    ]
    
    return any(trigger in question_lower for trigger in analysis_triggers)


def extract_years_from_question(question):
    """Extract years mentioned in the question"""
    import re
    years = re.findall(r'20\d{2}', question)
    years = [int(y) for y in years]
    years = sorted(set(years))
    
    if len(years) >= 2:
        return years[0], years[1]
    elif len(years) == 1:
        return years[0] - 1, years[0]
    else:
        return 2024, 2025


# ============== ANALYTICS FUNCTIONS ==============

def get_brand_analytics(conn, year=2025):
    """Get comprehensive brand analytics"""
    # Brand performance with targets
    query = f"""
    SELECT 
        s.Brand,
        SUM(s.Total_Amount) as Sales,
        COALESCE(SUM(t.Total_Target), 0) as Target,
        SUM(s.Total_Qty) as Quantity,
        SUM(s.Transaction_Count) as Transactions,
        COUNT(DISTINCT s.Customer_Name) as Customers,
        COUNT(DISTINCT s.Salesman) as Salesmen
    FROM sales_summary s
    LEFT JOIN target_summary t ON s.Brand = t.Brand 
        AND s.Salesman = t.Salesman 
        AND s.Month_and_Year = t.Month_and_Year
        AND s.Customer_Name = t.Customer_Name
    WHERE s.Year = {year}
    GROUP BY s.Brand
    ORDER BY Sales DESC
    """
    df = pd.read_sql_query(query, conn)
    df['Achievement'] = (df['Sales'] / df['Target'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    df['Gap'] = df['Target'] - df['Sales']
    return df

def get_gm_analytics(conn, year=2025):
    """Get GM (General Manager) performance analytics"""
    query = f"""
    SELECT 
        s.GM,
        SUM(s.Total_Amount) as Sales,
        COALESCE(SUM(t.Total_Target), 0) as Target,
        COUNT(DISTINCT s.Brand) as Brands,
        COUNT(DISTINCT s.Salesman) as Salesmen,
        COUNT(DISTINCT s.Customer_Name) as Customers,
        SUM(s.Total_Qty) as Quantity
    FROM sales_summary s
    LEFT JOIN target_summary t ON s.Brand = t.Brand 
        AND s.Salesman = t.Salesman 
        AND s.Month_and_Year = t.Month_and_Year
        AND s.Customer_Name = t.Customer_Name
    WHERE s.Year = {year} AND s.GM IS NOT NULL AND s.GM != ''
    GROUP BY s.GM
    ORDER BY Sales DESC
    """
    df = pd.read_sql_query(query, conn)
    df['Achievement'] = (df['Sales'] / df['Target'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    df['Gap'] = df['Target'] - df['Sales']
    return df

def get_salesman_analytics(conn, year=2025, gm_filter=None, brand_filter=None):
    """Get salesman performance analytics"""
    where_clause = f"WHERE s.Year = {year}"
    if gm_filter and gm_filter != "All":
        where_clause += f" AND s.GM = '{gm_filter}'"
    if brand_filter and brand_filter != "All":
        where_clause += f" AND s.Brand = '{brand_filter}'"
    
    query = f"""
    SELECT 
        s.Salesman,
        s.GM,
        s.Manager,
        SUM(s.Total_Amount) as Sales,
        COALESCE(SUM(t.Total_Target), 0) as Target,
        COUNT(DISTINCT s.Brand) as Brands,
        COUNT(DISTINCT s.Customer_Name) as Customers,
        SUM(s.Total_Qty) as Quantity,
        SUM(s.Transaction_Count) as Transactions
    FROM sales_summary s
    LEFT JOIN target_summary t ON s.Brand = t.Brand 
        AND s.Salesman = t.Salesman 
        AND s.Month_and_Year = t.Month_and_Year
        AND s.Customer_Name = t.Customer_Name
    {where_clause}
    GROUP BY s.Salesman, s.GM, s.Manager
    ORDER BY Sales DESC
    """
    df = pd.read_sql_query(query, conn)
    df['Achievement'] = (df['Sales'] / df['Target'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    df['Gap'] = df['Target'] - df['Sales']
    df['Avg_per_Customer'] = (df['Sales'] / df['Customers']).replace([np.inf, -np.inf], 0).fillna(0)
    return df

def get_account_analytics(conn, year=2025, salesman_filter=None, brand_filter=None):
    """Get customer/account performance analytics"""
    where_clause = f"WHERE s.Year = {year}"
    if salesman_filter and salesman_filter != "All":
        where_clause += f" AND s.Salesman = '{salesman_filter}'"
    if brand_filter and brand_filter != "All":
        where_clause += f" AND s.Brand = '{brand_filter}'"
    
    query = f"""
    SELECT 
        s.Customer_Name,
        s.Salesman,
        s.Emirate,
        s.Channel,
        SUM(s.Total_Amount) as Sales,
        COALESCE(SUM(t.Total_Target), 0) as Target,
        SUM(s.Total_Qty) as Quantity,
        SUM(s.Total_Bonus) as Bonus_Qty,
        SUM(s.Transaction_Count) as Transactions,
        COUNT(DISTINCT s.Brand) as Brands_Bought
    FROM sales_summary s
    LEFT JOIN target_summary t ON s.Brand = t.Brand 
        AND s.Salesman = t.Salesman 
        AND s.Month_and_Year = t.Month_and_Year
        AND s.Customer_Name = t.Customer_Name
    {where_clause}
    GROUP BY s.Customer_Name, s.Salesman, s.Emirate, s.Channel
    ORDER BY Sales DESC
    """
    df = pd.read_sql_query(query, conn)
    df['Achievement'] = (df['Sales'] / df['Target'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
    df['Gap'] = df['Target'] - df['Sales']
    return df

def get_monthly_trend(conn, year=2025, dimension=None, dimension_value=None):
    """Get monthly sales trend"""
    where_clause = f"WHERE Year = {year}"
    if dimension and dimension_value and dimension_value != "All":
        where_clause += f" AND {dimension} = '{dimension_value}'"
    
    query = f"""
    SELECT 
        Month_and_Year,
        Month_and_Year_Sort,
        SUM(Total_Amount) as Sales,
        SUM(Total_Qty) as Quantity
    FROM sales_summary
    {where_clause}
    GROUP BY Month_and_Year, Month_and_Year_Sort
    ORDER BY Month_and_Year_Sort
    """
    return pd.read_sql_query(query, conn)

def get_yoy_comparison(conn, brand=None, salesman=None):
    """Get year-over-year comparison"""
    where_clause = "WHERE 1=1"
    if brand and brand != "All":
        where_clause += f" AND Brand = '{brand}'"
    if salesman and salesman != "All":
        where_clause += f" AND Salesman = '{salesman}'"
    
    query = f"""
    SELECT 
        Year,
        SUM(Total_Amount) as Sales,
        SUM(Total_Qty) as Quantity,
        COUNT(DISTINCT Customer_Name) as Customers
    FROM sales_summary
    {where_clause}
    GROUP BY Year
    ORDER BY Year
    """
    return pd.read_sql_query(query, conn)

def generate_recommendations(df, entity_type, entity_name):
    """Generate AI-powered POWERFUL recommendations based on gap analysis & behavior"""
    recommendations = []
    
    if df.empty:
        return ["No data available for analysis"]
    
    # Calculate key metrics
    total_gap = df['Gap'].sum() if 'Gap' in df.columns else 0
    avg_achievement = df['Achievement'].mean() if 'Achievement' in df.columns else 0
    
    # 1. QUANTIFIED GAP CLOSING
    if total_gap > 0:
        daily_close = total_gap / 22 # Assuming 22 working days
        recommendations.append(f"🎯 **Gap Strategy**: Need AED {format_number(daily_close)}/day run-rate to hit target.")
    else:
        recommendations.append(f"🚀 **Momentum**: Exceeding target by AED {format_number(abs(total_gap))}! Upsell new lines.")

    if entity_type == "Brand":
        # 2. BRAND SPECIFIC TACTICS
        if avg_achievement < 80:
            recommendations.append(f"🔴 **Critical Action**: {entity_name} is at {avg_achievement:.1f}%.")
            recommendations.append("1. **Availability**: Audit OOS in top 20 accounts.")
            recommendations.append("2. **Investment**: Divert trade spend to this brand immediately.")
        elif avg_achievement < 95:
             recommendations.append(f"🟡 **Tactical Push**: {entity_name} is close ({avg_achievement:.1f}%).")
             recommendations.append("🔹 Action: Run 'Buy 2 Get 1' for last week of month.")
        
    elif entity_type == "Salesman":
        # 3. SALESMAN SPECIFIC COACHING
        if avg_achievement < 70:
            recommendations.append(f"🔴 **Coaching Required**: Achievement {avg_achievement:.1f}%.")
            recommendations.append("📋 **Audit**: Check top 5 non-buying accounts in route.")
            recommendations.append("🚶 **Activity**: Review Journey Plan compliance.")
        elif avg_achievement < 90:
            recommendations.append(f"🟡 **Focus Area**: Gap closing mode ({avg_achievement:.1f}%).")
            recommendations.append("🔹 Action: Target accounts buying Brand A but not Brand B (Croos-sell).")
            
    elif entity_type == "Account":
        # 4. ACCOUNT SPECIFIC MOVES
        if avg_achievement < 50:
            recommendations.append("🔴 **Risk Alert**: High risk of churn or credit issue.")
            recommendations.append("🤝 **Action**: Schedule Principal/Manager visit immediately.")
        elif avg_achievement < 80:
            recommendations.append("🟡 **Development**: Account under-indexing.")
            recommendations.append("📦 **Mix**: Propose 2 new SKUs to boost basket size.")
    
    return recommendations

def show_gap_analysis(df, title, key_column):
    """Display gap analysis with recommendations"""
    st.subheader(f"📊 Gap Analysis - {title}")
    
    # Filter to show only items with gaps
    gap_df = df[df['Gap'] > 0].sort_values('Gap', ascending=False).head(10)
    
    if gap_df.empty:
        st.success("✅ All targets are being met or exceeded!")
        return
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Gap chart
        fig = px.bar(
            gap_df,
            x=key_column,
            y='Gap',
            color='Achievement',
            color_continuous_scale='RdYlGn',
            title=f"Top 10 Gaps by {title}"
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("### 🎯 Priority Actions")
        for idx, row in gap_df.head(5).iterrows():
            achievement = row['Achievement']
            gap = row['Gap']
            name = row[key_column]
            
            if achievement < 50:
                status = "🔴"
                action = "Urgent review needed"
            elif achievement < 80:
                status = "🟡"
                action = "Increase focus"
            else:
                status = "🟠"
                action = "Close the gap"
            
            st.markdown(f"""
            {status} **{name[:20]}...**
            - Gap: AED {format_number(gap)}
            - Achievement: {achievement:.1f}%
            - Action: {action}
            """)



# ============== MAIN APPLICATION ==============

def main():
    st.set_page_config(
        page_title="Sales Analytics Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    # Check if database exists
    if not os.path.exists('sales_data.db'):
        st.error("Database not found! Please run `python create_database.py` first.")
        return
    
    # Sidebar navigation
    with st.sidebar:
        st.header("🧭 Navigation")
        page = st.radio(
            "Select Page",
            ["🤖 AI Query", "📈 Brand Analytics", "👔 GM Analytics", 
             "👤 Salesman Analytics", "🏢 Account Analytics", "📊 Gap Analysis"]
        )
        
        st.markdown("---")
        st.header("⚙️ Settings")
        api_key = st.text_input("OpenAI API Key", type="password", 
                                value=os.getenv("OPENAI_API_KEY", ""))
        
        # Year filter for analytics pages
        year_filter = st.selectbox("Analysis Year", [2025, 2024, 2023, 2022], index=0)
    
    conn = get_db_connection()
    
    # ============== AI QUERY PAGE ==============
    if page == "🤖 AI Query":
        st.title("📊 Sales Data AI Query Agent")
        st.markdown("Ask questions about sales data in natural language - I'll analyze and investigate, not just query!")
        
        with st.sidebar:
            st.markdown("---")
            st.header("💡 Example Questions")
            st.markdown("""
            **Simple Queries:**
            - Total sales by year
            - Top 10 brands by sales
            - Sales vs target for 2025
            
            **Deep Analysis (AI Investigation):**
            - Why is DUP brand growth slowing?
            - What are the non-growing items for DUP in 2024 vs 2025?
            - Explain the sales decline for [brand]
            - Compare DUP performance 2024 vs 2025
            - Which items are dragging down [brand] growth?
            
            **Coverage Analysis:**
            - What is DUP brand coverage in the last 12 months?
            - Which accounts bought DUP historically but not recently?
            - Show me coverage reach for 1Y, 2Y, 3Y, 4Y
            - Which customers stopped buying DUP?
            
            **OOS Detection:**
            - Which DUP items had no sales in the last 30 days?
            - Show me potential out-of-stock items for DUP
            - Which items stopped selling unexpectedly?
            - Supply chain issues for DUP brand
            
            **Pattern Analysis:**
            - Which DUP items show seasonality?
            - Is item X sales stable or fluctuating?
            - Show me seasonal items for DUP
            - Which items have abnormal patterns?
            """)
        
        user_question = st.text_input("🔍 Ask a question about sales data:", 
                                       placeholder="e.g., What are the non-growing items for DUP brand 2024 vs 2025?")
        
        # Analysis mode toggle
        analysis_mode = st.checkbox("🔬 Enable Deep Analysis Mode (AI Investigation)", value=True,
                                   help="When enabled, AI will investigate root causes and provide insights, not just run queries")
        
        if st.button("🚀 Analyze", type="primary") and user_question:
            if not api_key:
                st.error("Please enter your OpenAI API key in the sidebar")
            else:
                # Detect if this needs enhanced analytics (coverage, OOS, pattern)
                enhanced_intent = detect_enhanced_analytics_intent(user_question)
                needs_analysis = detect_analysis_intent(user_question) or analysis_mode
                detected_brand = detect_brand_in_question(user_question, conn)
                
                with st.spinner("🔍 Analyzing your question..."):
                    try:
                        # Check if this needs enhanced analytics first
                        if enhanced_intent['needs_enhanced']:
                            st.subheader(f"🔮 Enhanced Analytics: {enhanced_intent['type'].replace('_', ' ').title()}")
                            
                            with st.spinner(f"Running {enhanced_intent['type']} analysis..."):
                                enhanced_results = handle_enhanced_analytics(user_question, enhanced_intent, conn, api_key)
                                
                                # Display results based on type
                                if enhanced_results.get('error'):
                                    st.error(enhanced_results['error'])
                                else:
                                    st.info(enhanced_results['summary'])
                                    
                                    if enhanced_intent['type'] == 'comparison':
                                        df = enhanced_results['data']
                                        st.dataframe(df, use_container_width=True)
                                        
                                        # Visualize comparison
                                        fig = px.bar(df, x='Time_Window', y='Coverage_Count', color='Type', barmode='group',
                                                    title='Coverage Comparison: Brand vs Company')
                                        st.plotly_chart(fig, use_container_width=True)
                                        
                                        # AI Insight
                                        with st.spinner("Generating AI insights..."):
                                            data_context = f"Coverage Comparison:\n{df.to_string()}"
                                            insight = generate_ai_insight(api_key, user_question, data_context)
                                            st.markdown("### 🧠 AI Insight")
                                            st.markdown(insight)

                                    elif enhanced_intent['type'] == 'coverage':
                                        df = enhanced_results['data']
                                        st.dataframe(df, use_container_width=True)
                                        
                                        # Visualize coverage trend
                                        fig = px.line(df, x='Time_Window', y='Coverage_Count',
                                                     title='Coverage Trend Over Time',
                                                     markers=True)
                                        st.plotly_chart(fig, use_container_width=True)
                                        
                                        # AI Insight
                                        with st.spinner("Generating AI insights..."):
                                            data_context = f"Coverage Analysis:\n{df.to_string()}"
                                            insight = generate_ai_insight(api_key, user_question, data_context)
                                            st.markdown("### 🧠 AI Insight")
                                            st.markdown(insight)
                                    
                                    elif enhanced_intent['type'] == 'coverage_loss':
                                        df = enhanced_results.get('data')
                                        if df is not None and not df.empty:
                                            st.dataframe(df.head(20), use_container_width=True)
                                        
                                            if 'new_vs_lost' in enhanced_results:
                                                new_lost = enhanced_results['new_vs_lost']
                                                col1, col2, col3 = st.columns(3)
                                                with col1:
                                                    st.metric("New Customers", new_lost['New_Customers'])
                                                with col2:
                                                    st.metric("Lost Customers", new_lost['Lost_Customers'])
                                                with col3:
                                                    st.metric("Retained Customers", new_lost['Retained_Customers'])
                                            
                                            # AI Insight
                                            with st.spinner("Generating AI insights..."):
                                                data_context = f"Coverage Loss Analysis:\n{df.head(20).to_string()}\n\nNew vs Lost: {enhanced_results.get('new_vs_lost', {})}"
                                                insight = generate_ai_insight(api_key, user_question, data_context)
                                                st.markdown("### 🧠 AI Insight")
                                                st.markdown(insight)
                                        else:
                                            st.info("No coverage loss data found. Please specify a valid brand or item.")
                                    
                                    elif enhanced_intent['type'] == 'oos':
                                        df = enhanced_results['data']
                                        st.dataframe(df.head(20), use_container_width=True)
                                        
                                        if 'supply_issues' in enhanced_results and not enhanced_results['supply_issues'].empty:
                                            st.markdown("### ⚠️ Multi-Account OOS (Supply Issues)")
                                            st.dataframe(enhanced_results['supply_issues'].head(10), use_container_width=True)
                                        
                                        # Visualize OOS risk
                                        if not df.empty and 'OOS_Risk_Level' in df.columns:
                                            fig = px.bar(df.head(15), x='Item_Desc', y='Historical_Sales',
                                                        color='OOS_Risk_Level',
                                                        title='Potential OOS Items by Historical Sales',
                                                        color_discrete_map={'High': 'red', 'Medium': 'orange', 'Low': 'yellow'})
                                            fig.update_layout(xaxis_tickangle=-45)
                                            st.plotly_chart(fig, use_container_width=True)
                                        
                                        # AI Insight
                                        with st.spinner("Generating AI insights..."):
                                            data_context = f"OOS Detection:\n{df.head(20).to_string()}"
                                            if 'supply_issues' in enhanced_results:
                                                data_context += f"\n\nSupply Issues:\n{enhanced_results['supply_issues'].head(10).to_string()}"
                                            insight = generate_ai_insight(api_key, user_question, data_context)
                                            st.markdown("### 🧠 AI Insight")
                                            st.markdown(insight)
                                    
                                    elif enhanced_intent['type'] == 'pattern':
                                        df = enhanced_results['data']
                                        st.dataframe(df.head(20), use_container_width=True)
                                        
                                        if 'anomalies' in enhanced_results and not enhanced_results['anomalies'].empty:
                                            st.markdown("### 🔍 Detected Anomalies")
                                            st.dataframe(enhanced_results['anomalies'].head(10), use_container_width=True)
                                        
                                        # AI Insight
                                        with st.spinner("Generating AI insights..."):
                                            data_context = f"Pattern Analysis:\n{df.head(20).to_string()}"
                                            if 'anomalies' in enhanced_results:
                                                data_context += f"\n\nAnomalies:\n{enhanced_results['anomalies'].head(10).to_string()}"
                                            insight = generate_ai_insight(api_key, user_question, data_context)
                                            st.markdown("### 🧠 AI Insight")
                                            st.markdown(insight)
                                    
                                    elif enhanced_intent['type'] == 'supply_chain':
                                        dashboard = enhanced_results['data']
                                        
                                        # Display dashboard metrics
                                        col1, col2, col3, col4 = st.columns(4)
                                        with col1:
                                            st.metric("OOS Items", dashboard['oos_items_count'])
                                        with col2:
                                            st.metric("Supply Issues", dashboard['supply_issues_count'])
                                        with col3:
                                            st.metric("Coverage Loss", dashboard['coverage_loss_count'])
                                        with col4:
                                            st.metric("Seasonal Items", dashboard['seasonal_items_count'])
                                        
                                        # Show details in tabs
                                        tab1, tab2, tab3, tab4 = st.tabs(["OOS Items", "Supply Issues", "Coverage Loss", "Seasonal Items"])
                                        
                                        with tab1:
                                            if dashboard['oos_items']:
                                                st.dataframe(pd.DataFrame(dashboard['oos_items']).head(15), use_container_width=True)
                                        
                                        with tab2:
                                            if dashboard['supply_issues']:
                                                st.dataframe(pd.DataFrame(dashboard['supply_issues']).head(15), use_container_width=True)
                                        
                                        with tab3:
                                            if dashboard['coverage_loss']:
                                                st.dataframe(pd.DataFrame(dashboard['coverage_loss']).head(15), use_container_width=True)
                                        
                                        with tab4:
                                            if dashboard['seasonal_items']:
                                                st.dataframe(pd.DataFrame(dashboard['seasonal_items']).head(15), use_container_width=True)
                                        
                                        # AI Insight
                                        with st.spinner("Generating AI insights..."):
                                            data_context = f"Supply Chain Dashboard:\n{dashboard}"
                                            insight = generate_ai_insight(api_key, user_question, data_context)
                                            st.markdown("### 🧠 AI Insight")
                                            st.markdown(insight)
                        
                        else:
                            # Regular SQL query path
                            sql = generate_sql(user_question, api_key)
                            
                            with st.expander("📝 Generated SQL Query", expanded=False):
                                st.code(sql, language="sql")
                            
                            df, error = execute_query(sql)
                            
                            if error:
                                st.error(f"Query Error: {error}")
                            else:
                                st.subheader("📊 Query Results")
                                st.info(f"Found {len(df)} rows")
                                st.dataframe(df, use_container_width=True)
                                
                                # Check if this is a decline/growth analysis question
                                is_analysis_question = detect_decline_analysis_question(user_question)
                                
                                # If deep analysis is needed and brand detected
                                if (needs_analysis or is_analysis_question) and detected_brand:
                                    st.markdown("---")
                                    
                                    # Extract years from question
                                    year1, year2 = extract_years_from_question(user_question)
                                    
                                    # Determine if we need Brand_Mask (for BAYER) or regular Brand
                                    use_brand_mask = (detected_brand == 'BAYER_MASK')
                                    display_brand = 'BAYER' if use_brand_mask else detected_brand
                                    actual_brand = 'Bayer' if use_brand_mask else detected_brand
                                    
                                    # Detect if user is asking about growth or decline
                                    focus = detect_growth_or_decline_focus(user_question)
                                    
                                    st.subheader(f"🔬 AI Deep Analysis: {display_brand} ({year1} vs {year2})")
                                    
                                    with st.spinner(f"🧠 Investigating {display_brand} data..."):
                                        # Get comprehensive analysis using the GENERIC function
                                        analysis_results = get_comprehensive_brand_analysis(
                                            conn, 
                                            actual_brand, 
                                            year1, 
                                            year2, 
                                            use_brand_mask=use_brand_mask,
                                            focus=focus
                                        )
                                        
                                        # Display comprehensive analysis with all tables
                                        display_comprehensive_analysis(analysis_results, year1, year2)
                                        
                                        # AI Insight
                                        st.markdown("---")
                                        st.subheader("🧠 AI Insight & Root Cause Summary")
                                        
                                        with st.spinner("Generating AI insights..."):
                                            summary = analysis_results.get('summary', {})
                                            focus_context = analysis_results.get('focus', 'all')
                                            
                                            # Add focus context to the prompt
                                            focus_note = ""
                                            if focus_context == 'growing':
                                                focus_note = "\n\nIMPORTANT: User is asking about GROWTH/GROWING items. Focus on what's DRIVING GROWTH, not decline."
                                            elif focus_context == 'declining':
                                                focus_note = "\n\nIMPORTANT: User is asking about DECLINE/DECLINING items. Focus on what's CAUSING DECLINE, not growth."
                                            
                                            # Prepare comprehensive context for AI
                                            data_context = f"""
Brand: {display_brand}
{year1} Total Sales: AED {format_number(summary.get(f'total_{year1}', 0))}
{year2} Total Sales: AED {format_number(summary.get(f'total_{year2}', 0))}
Overall Growth: {summary.get('growth_pct', 0):.2f}% (AED {format_number(summary.get('growth_value', 0))})
{focus_note}

TOP ACCOUNT GROUPS:
{analysis_results['groups'].head(5).to_string() if analysis_results.get('groups') is not None and not analysis_results['groups'].empty else 'N/A'}

TOP ITEMS:
{analysis_results['items'].head(10).to_string() if analysis_results.get('items') is not None and not analysis_results['items'].empty else 'N/A'}

TOP CUSTOMERS:
{analysis_results['customers'].head(5).to_string() if analysis_results.get('customers') is not None and not analysis_results['customers'].empty else 'N/A'}

CHANNEL CONTRIBUTION:
{analysis_results['channels'].to_string() if analysis_results.get('channels') is not None and not analysis_results['channels'].empty else 'N/A'}

EMIRATE CONTRIBUTION:
{analysis_results['emirates'].to_string() if analysis_results.get('emirates') is not None and not analysis_results['emirates'].empty else 'N/A'}

SALESMAN CONTRIBUTION:
{analysis_results['salesman'].head(5).to_string() if analysis_results.get('salesman') is not None and not analysis_results['salesman'].empty else 'N/A'}
"""
                                            insight = generate_ai_insight(api_key, user_question, data_context, analysis_results)
                                            st.markdown(insight)
                                
                                elif needs_analysis and not detected_brand:
                                    # General analysis without specific brand
                                    st.markdown("---")
                                    st.info("💡 Tip: Mention a specific brand name for detailed item-level analysis (e.g., 'DUP', 'BAYER', 'Pfizer', etc.)")
                                    
                                    # Still provide AI insight on the query results
                                    with st.spinner("Generating AI insights..."):
                                        data_context = f"Query Results:\n{df.to_string()}"
                                        insight = generate_ai_insight(api_key, user_question, data_context)
                                        st.subheader("🧠 AI Insight")
                                        st.markdown(insight)
                                
                                csv = df.to_csv(index=False)
                                st.download_button("📥 Download CSV", csv, "results.csv", "text/csv")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
    
    # ============== BRAND ANALYTICS PAGE ==============
    elif page == "📈 Brand Analytics":
        st.title("📈 Brand Performance Analytics")
        
        brand_df = get_brand_analytics(conn, year_filter)
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Brands", len(brand_df))
        with col2:
            st.metric("Total Sales", f"AED {format_number(brand_df['Sales'].sum())}")
        with col3:
            st.metric("Total Target", f"AED {format_number(brand_df['Target'].sum())}")
        with col4:
            overall_ach = (brand_df['Sales'].sum() / brand_df['Target'].sum() * 100) if brand_df['Target'].sum() > 0 else 0
            st.metric("Overall Achievement", f"{overall_ach:.1f}%")
        
        st.markdown("---")
        
        # Charts Row 1
        col1, col2 = st.columns(2)
        
        with col1:
            # Top 10 Brands by Sales
            top_brands = brand_df.head(10)
            fig = px.bar(
                top_brands, x='Brand', y='Sales',
                title="Top 10 Brands by Sales",
                color='Achievement',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Sales vs Target
            fig = go.Figure()
            fig.add_trace(go.Bar(name='Sales', x=top_brands['Brand'], y=top_brands['Sales'], marker_color='#2E86AB'))
            fig.add_trace(go.Bar(name='Target', x=top_brands['Brand'], y=top_brands['Target'], marker_color='#A23B72'))
            fig.update_layout(title="Sales vs Target - Top 10 Brands", barmode='group', xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        # Charts Row 2
        col1, col2 = st.columns(2)
        
        with col1:
            # Achievement Distribution
            fig = px.histogram(
                brand_df, x='Achievement',
                nbins=20,
                title="Achievement Distribution Across Brands",
                color_discrete_sequence=['#2E86AB']
            )
            fig.add_vline(x=100, line_dash="dash", line_color="green", annotation_text="Target")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Brand Market Share
            fig = px.pie(
                top_brands, values='Sales', names='Brand',
                title="Market Share - Top 10 Brands"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Detailed Table
        st.subheader("📋 Brand Performance Details")
        display_df = brand_df[['Brand', 'Sales', 'Target', 'Achievement', 'Gap', 'Customers', 'Salesmen']].copy()
        display_df['Sales'] = display_df['Sales'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Target'] = display_df['Target'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Gap'] = display_df['Gap'].apply(lambda x: f"AED {format_number(x)}" if x > 0 else "✅ Met")
        display_df['Achievement'] = display_df['Achievement'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display_df, use_container_width=True)
        
        # Gap Analysis
        show_gap_analysis(brand_df, "Brands", "Brand")
    
    # ============== GM ANALYTICS PAGE ==============
    elif page == "👔 GM Analytics":
        st.title("👔 General Manager Performance Analytics")
        
        gm_df = get_gm_analytics(conn, year_filter)
        
        if gm_df.empty:
            st.warning("No GM data available for the selected year")
        else:
            # KPI Cards
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total GMs", len(gm_df))
            with col2:
                st.metric("Total Sales", f"AED {format_number(gm_df['Sales'].sum())}")
            with col3:
                st.metric("Avg Achievement", f"{gm_df['Achievement'].mean():.1f}%")
            with col4:
                st.metric("Total Salesmen", gm_df['Salesmen'].sum())
            
            st.markdown("---")
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(
                    gm_df, x='GM', y='Sales',
                    title="Sales by General Manager",
                    color='Achievement',
                    color_continuous_scale='RdYlGn'
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = go.Figure()
                fig.add_trace(go.Bar(name='Sales', x=gm_df['GM'], y=gm_df['Sales'], marker_color='#2E86AB'))
                fig.add_trace(go.Bar(name='Target', x=gm_df['GM'], y=gm_df['Target'], marker_color='#A23B72'))
                fig.update_layout(title="Sales vs Target by GM", barmode='group', xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            # GM Performance Radar
            col1, col2 = st.columns(2)
            
            with col1:
                # Team Size vs Performance
                fig = px.scatter(
                    gm_df, x='Salesmen', y='Achievement',
                    size='Sales', color='GM',
                    title="Team Size vs Achievement",
                    hover_data=['Customers', 'Brands']
                )
                fig.add_hline(y=100, line_dash="dash", line_color="green")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Achievement Gauge for Top GM
                top_gm = gm_df.iloc[0]
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=top_gm['Achievement'],
                    title={'text': f"Top GM: {top_gm['GM']}"},
                    delta={'reference': 100},
                    gauge={
                        'axis': {'range': [0, 150]},
                        'bar': {'color': "#2E86AB"},
                        'steps': [
                            {'range': [0, 70], 'color': "#FF6B6B"},
                            {'range': [70, 100], 'color': "#FFE66D"},
                            {'range': [100, 150], 'color': "#4ECDC4"}
                        ],
                        'threshold': {'line': {'color': "green", 'width': 4}, 'thickness': 0.75, 'value': 100}
                    }
                ))
                st.plotly_chart(fig, use_container_width=True)
            
            # Detailed Table
            st.subheader("📋 GM Performance Details")
            display_df = gm_df[['GM', 'Sales', 'Target', 'Achievement', 'Gap', 'Brands', 'Salesmen', 'Customers']].copy()
            display_df['Sales'] = display_df['Sales'].apply(lambda x: f"AED {format_number(x)}")
            display_df['Target'] = display_df['Target'].apply(lambda x: f"AED {format_number(x)}")
            display_df['Gap'] = display_df['Gap'].apply(lambda x: f"AED {format_number(x)}" if x > 0 else "✅ Met")
            display_df['Achievement'] = display_df['Achievement'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(display_df, use_container_width=True)
            
            # Gap Analysis
            show_gap_analysis(gm_df, "General Managers", "GM")
    
    # ============== SALESMAN ANALYTICS PAGE ==============
    elif page == "👤 Salesman Analytics":
        st.title("👤 Salesman Performance Analytics")
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            gms = pd.read_sql_query(f"SELECT DISTINCT GM FROM sales_summary WHERE Year = {year_filter} AND GM IS NOT NULL AND GM != '' ORDER BY GM", conn)
            gm_filter = st.selectbox("Filter by GM", ["All"] + gms['GM'].tolist())
        with col2:
            brands = pd.read_sql_query(f"SELECT DISTINCT Brand FROM sales_summary WHERE Year = {year_filter} ORDER BY Brand", conn)
            brand_filter = st.selectbox("Filter by Brand", ["All"] + brands['Brand'].tolist())
        
        salesman_df = get_salesman_analytics(conn, year_filter, gm_filter, brand_filter)
        
        # KPI Cards
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Salesmen", len(salesman_df))
        with col2:
            st.metric("Total Sales", f"AED {format_number(salesman_df['Sales'].sum())}")
        with col3:
            st.metric("Avg Achievement", f"{salesman_df['Achievement'].mean():.1f}%")
        with col4:
            above_target = len(salesman_df[salesman_df['Achievement'] >= 100])
            st.metric("Above Target", f"{above_target} ({above_target/len(salesman_df)*100:.0f}%)" if len(salesman_df) > 0 else "0")
        with col5:
            st.metric("Total Customers", salesman_df['Customers'].sum())
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            top_salesmen = salesman_df.head(15)
            fig = px.bar(
                top_salesmen, x='Salesman', y='Sales',
                title="Top 15 Salesmen by Sales",
                color='Achievement',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            fig = px.scatter(
                salesman_df, x='Customers', y='Sales',
                size='Transactions', color='Achievement',
                hover_name='Salesman',
                title="Customers vs Sales Performance",
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Achievement Distribution
            fig = px.histogram(
                salesman_df, x='Achievement',
                nbins=20,
                title="Achievement Distribution",
                color_discrete_sequence=['#2E86AB']
            )
            fig.add_vline(x=100, line_dash="dash", line_color="green", annotation_text="Target")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Avg per Customer
            top_avg = salesman_df.nlargest(10, 'Avg_per_Customer')
            fig = px.bar(
                top_avg, x='Salesman', y='Avg_per_Customer',
                title="Top 10 by Avg Sales per Customer",
                color='Avg_per_Customer',
                color_continuous_scale='Blues'
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        # Performance Categories
        st.subheader("📊 Performance Categories")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            stars = salesman_df[salesman_df['Achievement'] >= 100]
            st.markdown(f"### 🌟 Stars ({len(stars)})")
            st.markdown("Achievement ≥ 100%")
            if not stars.empty:
                for _, row in stars.head(5).iterrows():
                    st.markdown(f"- {row['Salesman']}: {row['Achievement']:.1f}%")
        
        with col2:
            potential = salesman_df[(salesman_df['Achievement'] >= 70) & (salesman_df['Achievement'] < 100)]
            st.markdown(f"### 🔶 Potential ({len(potential)})")
            st.markdown("Achievement 70-99%")
            if not potential.empty:
                for _, row in potential.head(5).iterrows():
                    st.markdown(f"- {row['Salesman']}: {row['Achievement']:.1f}%")
        
        with col3:
            needs_support = salesman_df[salesman_df['Achievement'] < 70]
            st.markdown(f"### 🔴 Needs Support ({len(needs_support)})")
            st.markdown("Achievement < 70%")
            if not needs_support.empty:
                for _, row in needs_support.head(5).iterrows():
                    st.markdown(f"- {row['Salesman']}: {row['Achievement']:.1f}%")
        
        # Detailed Table
        st.subheader("📋 Salesman Performance Details")
        display_df = salesman_df[['Salesman', 'GM', 'Sales', 'Target', 'Achievement', 'Gap', 'Customers', 'Brands']].copy()
        display_df['Sales'] = display_df['Sales'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Target'] = display_df['Target'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Gap'] = display_df['Gap'].apply(lambda x: f"AED {format_number(x)}" if x > 0 else "✅ Met")
        display_df['Achievement'] = display_df['Achievement'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display_df, use_container_width=True)
        
        # Gap Analysis
        show_gap_analysis(salesman_df, "Salesmen", "Salesman")

    
    # ============== ACCOUNT ANALYTICS PAGE ==============
    elif page == "🏢 Account Analytics":
        st.title("🏢 Account/Customer Performance Analytics")
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            salesmen = pd.read_sql_query(f"SELECT DISTINCT Salesman FROM sales_summary WHERE Year = {year_filter} ORDER BY Salesman", conn)
            salesman_filter = st.selectbox("Filter by Salesman", ["All"] + salesmen['Salesman'].tolist())
        with col2:
            brands = pd.read_sql_query(f"SELECT DISTINCT Brand FROM sales_summary WHERE Year = {year_filter} ORDER BY Brand", conn)
            brand_filter_acc = st.selectbox("Filter by Brand", ["All"] + brands['Brand'].tolist(), key="brand_acc")
        
        account_df = get_account_analytics(conn, year_filter, salesman_filter, brand_filter_acc)
        
        # KPI Cards
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Accounts", len(account_df))
        with col2:
            st.metric("Total Sales", f"AED {format_number(account_df['Sales'].sum())}")
        with col3:
            st.metric("Avg Achievement", f"{account_df['Achievement'].mean():.1f}%")
        with col4:
            active = len(account_df[account_df['Transactions'] >= 3])
            st.metric("Active Accounts", f"{active}")
        with col5:
            st.metric("Total Transactions", f"{format_number(account_df['Transactions'].sum())}")
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            top_accounts = account_df.head(15)
            fig = px.bar(
                top_accounts, x='Customer_Name', y='Sales',
                title="Top 15 Accounts by Sales",
                color='Achievement',
                color_continuous_scale='RdYlGn'
            )
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Sales by Emirate
            emirate_sales = account_df.groupby('Emirate').agg({'Sales': 'sum', 'Customer_Name': 'count'}).reset_index()
            emirate_sales.columns = ['Emirate', 'Sales', 'Accounts']
            fig = px.pie(
                emirate_sales, values='Sales', names='Emirate',
                title="Sales Distribution by Emirate"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Sales by Channel
            channel_sales = account_df.groupby('Channel').agg({'Sales': 'sum'}).reset_index()
            fig = px.bar(
                channel_sales, x='Channel', y='Sales',
                title="Sales by Channel",
                color='Sales',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Account Size Distribution
            account_df['Size_Category'] = pd.cut(
                account_df['Sales'],
                bins=[0, 10000, 50000, 200000, 1000000, float('inf')],
                labels=['Micro (<10K)', 'Small (10-50K)', 'Medium (50-200K)', 'Large (200K-1M)', 'Enterprise (>1M)']
            )
            size_dist = account_df['Size_Category'].value_counts().reset_index()
            size_dist.columns = ['Category', 'Count']
            fig = px.pie(
                size_dist, values='Count', names='Category',
                title="Account Size Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Account Health Analysis
        st.subheader("🏥 Account Health Analysis")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            healthy = account_df[account_df['Achievement'] >= 100]
            st.markdown(f"### 🟢 Healthy ({len(healthy)})")
            st.markdown(f"Total: AED {format_number(healthy['Sales'].sum())}")
            st.markdown("Meeting or exceeding targets")
        
        with col2:
            at_risk = account_df[(account_df['Achievement'] >= 50) & (account_df['Achievement'] < 100)]
            st.markdown(f"### 🟡 At Risk ({len(at_risk)})")
            st.markdown(f"Total: AED {format_number(at_risk['Sales'].sum())}")
            st.markdown("50-99% achievement")
        
        with col3:
            critical = account_df[account_df['Achievement'] < 50]
            st.markdown(f"### 🔴 Critical ({len(critical)})")
            st.markdown(f"Total: AED {format_number(critical['Sales'].sum())}")
            st.markdown("Below 50% achievement")
        
        # Top Underperforming Accounts
        st.subheader("⚠️ Top Underperforming Accounts (Biggest Gaps)")
        underperforming = account_df[account_df['Gap'] > 0].nlargest(10, 'Gap')
        if not underperforming.empty:
            for idx, row in underperforming.iterrows():
                with st.expander(f"🏢 {row['Customer_Name']} - Gap: AED {format_number(row['Gap'])}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Sales", f"AED {format_number(row['Sales'])}")
                    with col2:
                        st.metric("Target", f"AED {format_number(row['Target'])}")
                    with col3:
                        st.metric("Achievement", f"{row['Achievement']:.1f}%")
                    
                    st.markdown(f"""
                    **Details:**
                    - Salesman: {row['Salesman']}
                    - Emirate: {row['Emirate']}
                    - Channel: {row['Channel']}
                    - Transactions: {row['Transactions']}
                    - Brands Bought: {row['Brands_Bought']}
                    
                    **Recommendations:**
                    - Schedule business review meeting
                    - Analyze product mix opportunities
                    - Review pricing and promotions
                    - Increase visit frequency
                    """)
        
        # Detailed Table
        st.subheader("📋 Account Performance Details")
        display_df = account_df[['Customer_Name', 'Salesman', 'Emirate', 'Channel', 'Sales', 'Target', 'Achievement', 'Gap', 'Transactions']].head(100).copy()
        display_df['Sales'] = display_df['Sales'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Target'] = display_df['Target'].apply(lambda x: f"AED {format_number(x)}")
        display_df['Gap'] = display_df['Gap'].apply(lambda x: f"AED {format_number(x)}" if x > 0 else "✅ Met")
        display_df['Achievement'] = display_df['Achievement'].apply(lambda x: f"{x:.1f}%")
        st.dataframe(display_df, use_container_width=True)
    
    # ============== GAP ANALYSIS PAGE ==============
    elif page == "📊 Gap Analysis":
        st.title("📊 Comprehensive Gap Analysis & Recommendations")
        
        # Overall Summary
        st.header("📈 Overall Performance Summary")
        
        # Get all data
        brand_df = get_brand_analytics(conn, year_filter)
        gm_df = get_gm_analytics(conn, year_filter)
        salesman_df = get_salesman_analytics(conn, year_filter)
        account_df = get_account_analytics(conn, year_filter)
        
        total_sales = brand_df['Sales'].sum()
        total_target = brand_df['Target'].sum()
        total_gap = total_target - total_sales
        overall_achievement = (total_sales / total_target * 100) if total_target > 0 else 0
        
        # Executive Summary Cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sales", f"AED {format_number(total_sales)}")
        with col2:
            st.metric("Total Target", f"AED {format_number(total_target)}")
        with col3:
            delta_color = "normal" if overall_achievement >= 100 else "inverse"
            st.metric("Overall Achievement", f"{overall_achievement:.1f}%", 
                     delta=f"{overall_achievement - 100:.1f}%" if overall_achievement != 100 else None)
        with col4:
            st.metric("Total Gap", f"AED {format_number(total_gap)}" if total_gap > 0 else "✅ Target Met")
        
        st.markdown("---")
        
        # Gap Breakdown by Dimension
        st.header("🔍 Gap Breakdown Analysis")
        
        tab1, tab2, tab3, tab4 = st.tabs(["By Brand", "By GM", "By Salesman", "By Account"])
        
        with tab1:
            st.subheader("Brand Gap Analysis")
            brand_gaps = brand_df[brand_df['Gap'] > 0].sort_values('Gap', ascending=False)
            
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.treemap(
                    brand_gaps.head(20),
                    path=['Brand'],
                    values='Gap',
                    color='Achievement',
                    color_continuous_scale='RdYlGn',
                    title="Gap Distribution by Brand (Top 20)"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("### 🎯 Top 5 Brand Gaps")
                for idx, row in brand_gaps.head(5).iterrows():
                    st.markdown(f"""
                    **{row['Brand']}**
                    - Gap: AED {format_number(row['Gap'])}
                    - Achievement: {row['Achievement']:.1f}%
                    - Customers: {row['Customers']}
                    """)
                    st.markdown("---")
        
        with tab2:
            st.subheader("GM Gap Analysis")
            gm_gaps = gm_df[gm_df['Gap'] > 0].sort_values('Gap', ascending=False)
            
            if not gm_gaps.empty:
                col1, col2 = st.columns([2, 1])
                with col1:
                    fig = px.bar(
                        gm_gaps,
                        x='GM', y='Gap',
                        color='Achievement',
                        color_continuous_scale='RdYlGn_r',
                        title="Gap by General Manager"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### 🎯 GM Action Items")
                    for idx, row in gm_gaps.iterrows():
                        status = "🔴" if row['Achievement'] < 70 else "🟡" if row['Achievement'] < 100 else "🟢"
                        st.markdown(f"""
                        {status} **{row['GM']}**
                        - Gap: AED {format_number(row['Gap'])}
                        - Team Size: {row['Salesmen']} salesmen
                        - Action: {'Urgent intervention' if row['Achievement'] < 70 else 'Focus improvement'}
                        """)
        
        with tab3:
            st.subheader("Salesman Gap Analysis")
            salesman_gaps = salesman_df[salesman_df['Gap'] > 0].sort_values('Gap', ascending=False)
            
            col1, col2 = st.columns(2)
            with col1:
                fig = px.scatter(
                    salesman_gaps.head(50),
                    x='Customers', y='Gap',
                    size='Sales', color='Achievement',
                    hover_name='Salesman',
                    color_continuous_scale='RdYlGn',
                    title="Salesman Gap vs Customer Count"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Categorize salesmen
                categories = {
                    'High Gap, Few Customers': salesman_gaps[(salesman_gaps['Gap'] > salesman_gaps['Gap'].median()) & (salesman_gaps['Customers'] < salesman_gaps['Customers'].median())],
                    'High Gap, Many Customers': salesman_gaps[(salesman_gaps['Gap'] > salesman_gaps['Gap'].median()) & (salesman_gaps['Customers'] >= salesman_gaps['Customers'].median())],
                    'Low Gap, Few Customers': salesman_gaps[(salesman_gaps['Gap'] <= salesman_gaps['Gap'].median()) & (salesman_gaps['Customers'] < salesman_gaps['Customers'].median())],
                    'Low Gap, Many Customers': salesman_gaps[(salesman_gaps['Gap'] <= salesman_gaps['Gap'].median()) & (salesman_gaps['Customers'] >= salesman_gaps['Customers'].median())]
                }
                
                st.markdown("### 📊 Salesman Categories")
                for cat, df in categories.items():
                    st.markdown(f"**{cat}:** {len(df)} salesmen")
        
        with tab4:
            st.subheader("Account Gap Analysis")
            account_gaps = account_df[account_df['Gap'] > 0].sort_values('Gap', ascending=False)
            
            col1, col2 = st.columns(2)
            with col1:
                # Top 20 account gaps
                fig = px.bar(
                    account_gaps.head(20),
                    x='Customer_Name', y='Gap',
                    color='Achievement',
                    color_continuous_scale='RdYlGn',
                    title="Top 20 Account Gaps"
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Gap by Emirate
                emirate_gaps = account_gaps.groupby('Emirate').agg({'Gap': 'sum', 'Customer_Name': 'count'}).reset_index()
                emirate_gaps.columns = ['Emirate', 'Total_Gap', 'Accounts']
                fig = px.pie(
                    emirate_gaps, values='Total_Gap', names='Emirate',
                    title="Gap Distribution by Emirate"
                )
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        
        # Strategic Recommendations
        st.header("💡 Strategic Recommendations")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎯 Immediate Actions (This Month)")
            
            # Top 5 accounts to focus on
            top_gap_accounts = account_df[account_df['Gap'] > 0].nlargest(5, 'Gap')
            st.markdown("**Priority Accounts to Visit:**")
            for idx, row in top_gap_accounts.iterrows():
                st.markdown(f"- {row['Customer_Name']} (Gap: AED {format_number(row['Gap'])})")
            
            # Underperforming salesmen
            low_performers = salesman_df[salesman_df['Achievement'] < 70].nsmallest(5, 'Achievement')
            st.markdown("\n**Salesmen Needing Support:**")
            for idx, row in low_performers.iterrows():
                st.markdown(f"- {row['Salesman']} ({row['Achievement']:.1f}% achievement)")
        
        with col2:
            st.subheader("📈 Growth Opportunities")
            
            # Brands with high potential
            high_potential = brand_df[(brand_df['Achievement'] >= 80) & (brand_df['Achievement'] < 100)].nlargest(5, 'Gap')
            st.markdown("**Brands Close to Target (Quick Wins):**")
            for idx, row in high_potential.iterrows():
                st.markdown(f"- {row['Brand']} (Need AED {format_number(row['Gap'])} more)")
            
            # High-value accounts below target
            high_value_gap = account_df[(account_df['Target'] > account_df['Target'].quantile(0.75)) & (account_df['Achievement'] < 100)].nlargest(5, 'Target')
            st.markdown("\n**High-Value Accounts Below Target:**")
            for idx, row in high_value_gap.iterrows():
                st.markdown(f"- {row['Customer_Name']} ({row['Achievement']:.1f}%)")
        
        # Detailed Recommendations by Category
        st.subheader("📋 Detailed Action Plan")
        
        with st.expander("🔴 Critical Issues (Immediate Attention Required)"):
            critical_brands = brand_df[brand_df['Achievement'] < 50]
            critical_salesmen = salesman_df[salesman_df['Achievement'] < 50]
            
            st.markdown(f"""
            **Brands Below 50% Achievement:** {len(critical_brands)}
            - These brands need immediate product/pricing review
            - Consider promotional activities or bundle offers
            - Review distribution coverage
            
            **Salesmen Below 50% Achievement:** {len(critical_salesmen)}
            - Schedule one-on-one coaching sessions
            - Review territory assignments
            - Provide additional training and support
            - Consider route optimization
            """)
        
        with st.expander("🟡 Areas for Improvement (70-99% Achievement)"):
            improving_brands = brand_df[(brand_df['Achievement'] >= 70) & (brand_df['Achievement'] < 100)]
            
            st.markdown(f"""
            **Brands in Improvement Zone:** {len(improving_brands)}
            - Focus on top 20% customers for each brand
            - Implement targeted promotions
            - Increase visit frequency to key accounts
            - Cross-sell opportunities with performing brands
            
            **Key Actions:**
            1. Identify top 10 accounts per brand with highest gap
            2. Create account-specific action plans
            3. Weekly progress tracking
            4. Incentive programs for closing gaps
            """)
        
        with st.expander("🟢 Best Practices (From Top Performers)"):
            top_salesmen = salesman_df[salesman_df['Achievement'] >= 100].nlargest(5, 'Sales')
            
            st.markdown("**Top Performing Salesmen:**")
            for idx, row in top_salesmen.iterrows():
                st.markdown(f"- {row['Salesman']}: {row['Achievement']:.1f}% achievement, {row['Customers']} customers")
            
            st.markdown("""
            **Success Factors to Replicate:**
            1. Higher customer visit frequency
            2. Better product mix per customer
            3. Strong relationship management
            4. Effective use of promotions
            5. Consistent follow-up on orders
            """)
        
        # Export Options
        st.markdown("---")
        st.subheader("📥 Export Reports")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            csv = brand_df.to_csv(index=False)
            st.download_button("Download Brand Report", csv, "brand_analysis.csv", "text/csv")
        with col2:
            csv = salesman_df.to_csv(index=False)
            st.download_button("Download Salesman Report", csv, "salesman_analysis.csv", "text/csv")
        with col3:
            csv = account_df.to_csv(index=False)
            st.download_button("Download Account Report", csv, "account_analysis.csv", "text/csv")
    
    conn.close()

if __name__ == "__main__":
    main()
