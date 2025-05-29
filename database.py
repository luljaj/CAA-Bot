import sqlite3
import os

db_folder = './databases'
db_file = os.path.join(db_folder,'database.db')
conn = sqlite3.connect(db_file)
cursor = conn.cursor()


cursor.execute('''
ALTER TABLE stats
  DROP COLUMN reports;
''')



conn.commit()
conn.close()