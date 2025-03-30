import sqlite3
import os

db_folder = './databases'
db_file = os.path.join(db_folder,'applications.db')
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discordid INT,
    username TEXT,
    reason TEXT,
    inviter TEXT,
    status TEXT DEFAULT 'pending'
)
''')


conn.commit()
conn.close()