from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.services.auth import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password.")
    return TokenResponse(access_token=create_access_token(user.username))


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
