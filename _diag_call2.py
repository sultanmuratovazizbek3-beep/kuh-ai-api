import sqlite3
from datetime import datetime

con = sqlite3.connect("data/analytics.db")
con.row_factory = sqlite3.Row
print("duration=74 calls:")
for r in con.execute(
    """
    SELECT id, lead_id, duration, direction, created_at,
           datetime(created_at,'unixepoch','localtime') AS dt,
           length(coalesce(transcript,'')) AS tl,
           substr(coalesce(text,''),1,100) AS tx,
           substr(coalesce(recording_url,''),1,100) AS ru,
           transcript_status
    FROM communications
    WHERE kind='call' AND duration=74
    ORDER BY created_at DESC LIMIT 20
    """
):
    print(dict(r))

# also event-style calls with duration
print("\nevent calls with duration:")
for r in con.execute(
    """
    SELECT id, lead_id, duration, text, recording_url, created_at,
           datetime(created_at,'unixepoch','localtime') AS dt
    FROM communications
    WHERE kind='call' AND id LIKE 'event:%' AND COALESCE(duration,0)>0
    ORDER BY created_at DESC LIMIT 10
    """
):
    print(dict(r))
