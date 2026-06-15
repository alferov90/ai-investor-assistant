from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


@router.get("/history", response_model=list[schemas.AnalysisRecordRead])
def analysis_history(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.list_analyses(db, current_user.id, ticker=ticker, limit=limit)


@router.get("/history/{record_id}", response_model=schemas.AnalysisRecordRead)
def get_analysis_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi import HTTPException

    record = crud.get_analysis_record(db, current_user.id, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return record
