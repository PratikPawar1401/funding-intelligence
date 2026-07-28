from foa_pipeline.database import Database
from foa_pipeline.config import get_config
import json
db = Database(get_config().sqlite_db_path)
rows = db.conn.execute("SELECT foa_id, raw_payload FROM foa_records WHERE raw_payload LIKE '%\"pdf_links\": [\"%' LIMIT 1").fetchall()
if rows:
    row = rows[0]
    raw = row["raw_payload"] or "{}"
    print("foa_id:", row["foa_id"])
    payload = json.loads(raw)
    if isinstance(payload, str):
        payload = json.loads(payload)
    print("KEYS:", list(payload.keys()))
    print("PDF LINKS:", payload.get("pdf_links"))
    if "raw_payload" in payload:
        inner = payload["raw_payload"]
        if isinstance(inner, dict):
            print("INNER PDF LINKS:", inner.get("pdf_links"))
