from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

CONDITION_LABELS = {
    "above": "Цена выше",
    "below": "Цена ниже",
    "change_up": "Рост за день ≥",
    "change_down": "Падение за день ≥",
}


@router.get("", response_model=list[schemas.AlertRead])
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.list_alerts(db, current_user.id)


@router.post("", response_model=schemas.AlertRead, status_code=status.HTTP_201_CREATED)
def create_alert(
    data: schemas.AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.create_alert(db, current_user.id, data)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = crud.get_alert(db, current_user.id, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    crud.delete_alert(db, alert)


@router.patch("/{alert_id}/toggle", response_model=schemas.AlertRead)
def toggle_alert(
    alert_id: int,
    active: bool = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = crud.get_alert(db, current_user.id, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return crud.toggle_alert(db, alert, active)
