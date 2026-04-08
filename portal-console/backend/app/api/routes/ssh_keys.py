from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_admin
from app.models.server import Server
from app.models.ssh_key import SSHKey
from app.schemas.ssh_key import SSHKeyRead
from app.services.ssh_key_store import delete_private_key, store_private_key

router = APIRouter(prefix="/ssh-keys", tags=["ssh-keys"])


def build_ssh_key_read(ssh_key: SSHKey) -> SSHKeyRead:
    return SSHKeyRead(
        id=ssh_key.id,
        name=ssh_key.name,
        note=ssh_key.note,
        original_filename=ssh_key.original_filename,
        created_at=ssh_key.created_at,
        updated_at=ssh_key.updated_at,
        server_count=len(ssh_key.servers),
    )


def ensure_unique_name(db: Session, name: str, current_id: int | None = None) -> None:
    existing = db.scalar(select(SSHKey).where(SSHKey.name == name))
    if existing is not None and existing.id != current_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSH key name already exists.",
        )


@router.get("", response_model=list[SSHKeyRead])
def list_ssh_keys(
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[SSHKeyRead]:
    ssh_keys = db.scalars(
        select(SSHKey).options(selectinload(SSHKey.servers)).order_by(SSHKey.name)
    ).all()
    return [build_ssh_key_read(item) for item in ssh_keys]


@router.post("", response_model=SSHKeyRead, status_code=status.HTTP_201_CREATED)
def create_ssh_key(
    name: str = Form(...),
    note: str | None = Form(default=None),
    private_key: UploadFile = File(...),
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SSHKeyRead:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSH key name is required.",
        )
    ensure_unique_name(db, cleaned_name)
    try:
        stored_filename, original_filename = store_private_key(private_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    ssh_key = SSHKey(
        name=cleaned_name,
        note=note.strip() if note else None,
        original_filename=original_filename,
        stored_filename=stored_filename,
    )
    db.add(ssh_key)
    db.commit()
    db.refresh(ssh_key)
    return build_ssh_key_read(ssh_key)


@router.put("/{ssh_key_id}", response_model=SSHKeyRead)
def update_ssh_key(
    ssh_key_id: int,
    name: str | None = Form(default=None),
    note: str | None = Form(default=None),
    private_key: UploadFile | None = File(default=None),
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SSHKeyRead:
    ssh_key = db.scalar(
        select(SSHKey).where(SSHKey.id == ssh_key_id).options(selectinload(SSHKey.servers))
    )
    if ssh_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSH key not found.",
        )

    if name is not None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SSH key name is required.",
            )
        ensure_unique_name(db, cleaned_name, current_id=ssh_key.id)
        ssh_key.name = cleaned_name
    if note is not None:
        ssh_key.note = note.strip() or None
    if private_key is not None and private_key.filename:
        try:
            stored_filename, original_filename = store_private_key(
                private_key,
                existing_stored_filename=ssh_key.stored_filename,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        ssh_key.stored_filename = stored_filename
        ssh_key.original_filename = original_filename

    db.commit()
    db.refresh(ssh_key)
    return build_ssh_key_read(ssh_key)


@router.delete("/{ssh_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ssh_key(
    ssh_key_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    ssh_key = db.scalar(
        select(SSHKey).where(SSHKey.id == ssh_key_id).options(selectinload(SSHKey.servers))
    )
    if ssh_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSH key not found.",
        )
    in_use = db.scalar(select(Server).where(Server.ssh_key_id == ssh_key_id))
    if in_use is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSH key is still assigned to a server.",
        )

    delete_private_key(ssh_key.stored_filename)
    db.delete(ssh_key)
    db.commit()
