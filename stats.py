import sqlite3
import os

db_folder = './databases'
db_file = os.path.join(db_folder,'stats.db')
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discordid INT,
    username TEXT,
    cash INT DEFAULT 0,
    reports INT DEFAULT 0,
    eventswon INT DEFAULT 0
)
''')


conn.commit()
conn.close()