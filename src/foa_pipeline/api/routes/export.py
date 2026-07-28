"""Export endpoints: CSV and JSON download."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..deps import get_db
from ...database import Database
from ...csv_exporter import export_foas_to_csv

router = APIRouter()


@router.get("/csv")
def export_csv(
    status: Optional[str] = Query(default=None),
    agency: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
):
    """Download FOAs as CSV with tag evidence."""
    records, _ = db.list_foas(
        status=status,
        agency_code=agency,
        page=1,
        size=100000,
    )

    csv_content = export_foas_to_csv(records)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=foa_export.csv"},
    )


@router.get("/json")
def export_json(
    status: Optional[str] = Query(default=None),
    agency: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
):
    """Download FOAs as JSON."""
    records, total = db.list_foas(
        status=status,
        agency_code=agency,
        page=1,
        size=100000,
    )

    for r in records:
        r.pop("raw_payload", None)

    return {"foas": records, "total": total}
