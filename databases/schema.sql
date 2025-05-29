
CREATE TABLE IF NOT EXISTS "stats" (
    id SERIAL PRIMARY KEY,
    discordid BIGINT UNIQUE,
    username TEXT,
    eventswon INT DEFAULT 0
, awards TEXT DEFAULT '[]');
CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    discordid BIGINT,
    username TEXT,
    reason TEXT,
    inviter TEXT,
    FOREIGN KEY (discordid) REFERENCES stats(discordid)
);
