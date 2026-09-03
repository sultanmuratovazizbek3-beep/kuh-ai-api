import sqlite3
from pathlib import Path

con = sqlite3.connect("data/analytics.db")
con.row_factory = sqlite3.Row

# Find 74s incoming calls around that pattern
rows = con.execute(
    """
    SELECT id, lead_id, kind, direction, duration, created_at,
           length(coalesce(transcript,'')) tl,
           substr(coalesce(text,''),1,120) tx,
           substr(coalesce(recording_url,''),1,100) ru,
           transcript_status
    FROM communications
    WHERE kind='call' AND duration BETWEEN 70 AND 80
    ORDER BY created_at DESC LIMIT 20
    """
).fetchall()
print("74s-ish calls:", len(rows))
for r in rows[:10]:
    print(dict(r))

# any call with duration but empty recording
n = con.execute(
    """
    SELECT COUNT(*) FROM communications
    WHERE kind='call' AND COALESCE(duration,0) > 10
      AND (recording_url IS NULL OR recording_url='')
    """
).fetchone()[0]
print("calls >10s without recording_url:", n)

n2 = con.execute(
    """
    SELECT COUNT(*) FROM communications
    WHERE kind='call' AND COALESCE(duration,0) > 10
      AND recording_url IS NOT NULL AND recording_url!=''
      AND (transcript IS NULL OR length(trim(transcript))<10)
    """
).fetchone()[0]
print("calls with url but no transcript:", n2)

# recent empty-transcript calls with duration
print("\nsample no-transcript with duration:")
for r in con.execute(
    """
    SELECT id, lead_id, duration, direction,
           substr(coalesce(recording_url,''),1,80) ru,
           substr(coalesce(text,''),1,80) tx,
           transcript_status
    FROM communications
    WHERE kind='call' AND COALESCE(duration,0)>=30
      AND (transcript IS NULL OR length(trim(coalesce(transcript,'')))<10)
    ORDER BY created_at DESC LIMIT 15
    """
):
    print(dict(r))
