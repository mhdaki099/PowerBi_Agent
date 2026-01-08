"""
Script to create SQLite database from Excel file with multiple sheets
"""
import pandas as pd
import sqlite3
import os

def clean_columns(df):
    """Clean column names for SQL compatibility"""
    df.columns = [col.replace(' ', '_').replace('&', 'and').replace('.', '') for col in df.columns]
    return df

def create_database():
    # Remove old database if exists
    if os.path.exists('sales_data.db'):
        os.remove('sales_data.db')
        print("Removed old database")
    
    print("Reading Excel file...")
    xl = pd.ExcelFile('Conso_Sales with invoice.xlsx')
    print(f"Found sheets: {xl.sheet_names}")
    
    conn = sqlite3.connect('sales_data.db')
    cursor = conn.cursor()
    
    # Process Sales sheets one by one (to avoid memory issues)
    sales_sheets = ['2022 Sales', '2023 Sales', '2024 Sales', '2025 Sales']
    first_sheet = True
    total_sales = 0
    
    for sheet in sales_sheets:
        print(f"\nProcessing {sheet}...")
        df = pd.read_excel(xl, sheet_name=sheet)
        df = clean_columns(df)
        year = sheet.split()[0]
        df['Year'] = int(year)
        
        # Write to database (append after first)
        mode = 'replace' if first_sheet else 'append'
        df.to_sql('sales', conn, if_exists=mode, index=False, chunksize=50000)
        first_sheet = False
        total_sales += len(df)
        print(f"  {len(df):,} rows written")
    
    print(f"\nTotal sales records: {total_sales:,}")

    # Create indexes for sales table
    print("Creating indexes for sales...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(Invoice_Date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(Customer_Name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_brand ON sales(Brand)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_month ON sales(Month_and_Year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_year ON sales(Year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_emirate ON sales(Emirate)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sales_salesman ON sales(Salesman)')
    conn.commit()
    
    # Process Target sheet
    print("\nProcessing 2025 Target...")
    df_target = pd.read_excel(xl, sheet_name='2025 Target')
    df_target = clean_columns(df_target)
    df_target.to_sql('target', conn, if_exists='replace', index=False, chunksize=50000)
    print(f"  {len(df_target):,} rows written")
    
    # Create indexes for target table
    print("Creating indexes for target...")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_target_month ON target(Month_and_Year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_target_brand ON target(Brand)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_target_salesman ON target(Salesman)')
    conn.commit()
    
    # Verify and show summary
    print("\n" + "="*50)
    print("DATABASE SUMMARY")
    print("="*50)
    
    cursor.execute("SELECT COUNT(*) FROM sales")
    print(f"\nSales table: {cursor.fetchone()[0]:,} records")
    
    cursor.execute("SELECT Year, COUNT(*) as cnt FROM sales GROUP BY Year ORDER BY Year")
    print("  By Year:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]:,} records")
    
    cursor.execute("SELECT COUNT(*) FROM target")
    print(f"\nTarget table: {cursor.fetchone()[0]:,} records")
    
    print("\n--- Sales Table Columns ---")
    cursor.execute("PRAGMA table_info(sales)")
    cols = [col[1] for col in cursor.fetchall()]
    print(f"  {', '.join(cols)}")
    
    print("\n--- Target Table Columns ---")
    cursor.execute("PRAGMA table_info(target)")
    cols = [col[1] for col in cursor.fetchall()]
    print(f"  {', '.join(cols)}")
    
    conn.close()
    print("\n✓ Database saved as 'sales_data.db'")

if __name__ == "__main__":
    create_database()
