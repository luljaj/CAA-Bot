import sqlite3
import os

db_folder = './databases'
db_file = os.path.join(db_folder,'database.db')
conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discordid INT UNIQUE,
    username TEXT,
    cash INT DEFAULT 50,
    reports INT DEFAULT 0,
    eventswon INT DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discordid INT,
    username TEXT,
    reason TEXT,
    inviter TEXT,
    FOREIGN KEY (discordid) REFERENCES stats(discordid)
)
''')



conn.commit()
conn.close()