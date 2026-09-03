from fastapi.testclient import TestClient
from api_server import app
import sqlite3

c = TestClient(app)
lid = 30640849
con = sqlite3.connect("data/analytics.db")
con.row_factory = sqlite3.Row
print(
    "local by kind",
    con.execute(
        "SELECT kind, COUNT(*) n FROM communications WHERE lead_id=? GROUP BY kind",
        (lid,),
    ).fetchall(),
)
rows = con.execute(
    """
    SELECT id, kind, length(coalesce(transcript,'')) tl,
           length(coalesce(text,'')) tx,
           substr(coalesce(text,''),1,120) t,
           substr(coalesce(recording_url,''),1,40) ru
    FROM communications WHERE lead_id=? ORDER BY created_at DESC LIMIT 12
    """,
    (lid,),
).fetchall()
print("samples:")
for r in rows:
    print(dict(r))

a = c.get(f"/api/v1/crm/assist/{lid}").json()
print("stats", a.get("stats"))
print("conv n", len(a.get("conversation") or []))
print("hist n", len(a.get("history_preview") or []))
for h in (a.get("history_preview") or [])[:8]:
    print(" H", h.get("kind"), repr((h.get("text") or "")[:120]))
print("coach score", (a.get("coach") or {}).get("score"))
print("summary", str((a.get("coach") or {}).get("summary"))[:200])
