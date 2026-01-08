
import sqlite3
import sys

try:
    conn = sqlite3.connect('sales_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT type, sql FROM sqlite_master WHERE name='sales'")
    row = cursor.fetchone()
    print(f"Type: {row[0]}")
    print(f"SQL: {row[1]}")
    conn.close()
except Exception as e:
    print(e)
