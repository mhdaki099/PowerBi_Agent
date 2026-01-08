import sqlite3

conn = sqlite3.connect('sales_data.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM sales')
print(f'Total sales records: {cursor.fetchone()[0]:,}')

cursor.execute('SELECT COUNT(DISTINCT Brand) FROM sales')
print(f'Total brands: {cursor.fetchone()[0]}')

cursor.execute('SELECT Brand, COUNT(*) as cnt FROM sales GROUP BY Brand ORDER BY cnt DESC LIMIT 5')
print('\nTop 5 brands by record count:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]:,}')

conn.close()
print('\n✅ Database is accessible and has data!')
